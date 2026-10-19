from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from .tool_spec import SUPPORTED_RESULT_TYPES, ToolArgumentError, ToolRegistry


ACTION_TYPES = {"direct_answer", "tool_call", "workflow", "clarification", "abstain"}
VERIFICATION_POLICIES = {"auto", "required", "skip"}
REFERENCE_PATTERN = re.compile(
    r"^\$\{(?P<step>[A-Za-z][A-Za-z0-9_-]*)\.artifacts\.(?P<artifact>[A-Za-z][A-Za-z0-9_]*)\}$"
)
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
STEP_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
MAX_STEP_ID_LENGTH = 48


class AgentActionError(ValueError):
    """Raised when an Agent request or action violates its contract."""


def _require_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise AgentActionError(f"{field_name} must be an object")
    return dict(value)


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentActionError(f"{field_name} must be a non-empty string")
    return value.strip()


def _string_tuple(value: Any, field_name: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise AgentActionError(f"{field_name} must be a list of non-empty strings")
    normalized = tuple(item.strip() for item in value)
    if len(set(normalized)) != len(normalized):
        raise AgentActionError(f"{field_name} must not contain duplicates")
    return normalized


def _validate_verification_policy(value: Any, field_name: str) -> str:
    policy = str(value if value is not None else "auto").strip()
    if policy not in VERIFICATION_POLICIES:
        raise AgentActionError(f"{field_name} must be one of {sorted(VERIFICATION_POLICIES)}")
    return policy


def _validate_tool_call(
    tool_name: str,
    arguments: Mapping[str, Any],
    verification: str,
    registry: ToolRegistry,
    field_name: str,
) -> None:
    try:
        tool = registry.get(tool_name)
    except KeyError as exc:
        raise AgentActionError(f"{field_name}.tool references unknown tool {tool_name!r}") from exc
    try:
        tool.validate_arguments(arguments)
    except ToolArgumentError as exc:
        raise AgentActionError(f"Invalid {field_name}.arguments: {exc}") from exc
    if verification == "required" and tool.verifier is None:
        raise AgentActionError(
            f"{field_name}.verification is required, but {tool_name!r} has no registered verifier"
        )


def _find_artifact_references(value: Any) -> Tuple[Tuple[str, str], ...]:
    references = []
    if isinstance(value, str):
        match = REFERENCE_PATTERN.fullmatch(value)
        if match:
            references.append((match.group("step"), match.group("artifact")))
    elif isinstance(value, Mapping):
        for child in value.values():
            references.extend(_find_artifact_references(child))
    elif isinstance(value, list):
        for child in value:
            references.extend(_find_artifact_references(child))
    return tuple(references)


@dataclass(frozen=True)
class ExpectedOutput:
    type: str
    coordinate_space: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExpectedOutput":
        result_type = _require_string(payload.get("type"), "expected_output.type")
        if result_type not in SUPPORTED_RESULT_TYPES and result_type != "text":
            raise AgentActionError(
                f"expected_output.type must be text or one of {sorted(SUPPORTED_RESULT_TYPES)}"
            )
        return cls(
            type=result_type,
            coordinate_space=_require_string(
                payload.get("coordinate_space"), "expected_output.coordinate_space"
            ),
        )


@dataclass(frozen=True)
class DirectAnswerAction:
    answer: str
    type: str = field(default="direct_answer", init=False)


@dataclass(frozen=True)
class ToolCallAction:
    tool: str
    arguments: Dict[str, Any]
    verification: str = "auto"
    type: str = field(default="tool_call", init=False)


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    tool: str
    arguments: Dict[str, Any]
    depends_on: Tuple[str, ...] = ()
    verification: str = "auto"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], index: int) -> "WorkflowStep":
        prefix = f"action.steps[{index}]"
        step_id = _require_string(payload.get("step_id"), f"{prefix}.step_id")
        if not STEP_ID_PATTERN.fullmatch(step_id) or len(step_id) > MAX_STEP_ID_LENGTH:
            raise AgentActionError(f"{prefix}.step_id has an invalid identifier format")
        arguments = _require_mapping(payload.get("arguments"), f"{prefix}.arguments")
        return cls(
            step_id=step_id,
            tool=_require_string(payload.get("tool"), f"{prefix}.tool"),
            arguments=arguments,
            depends_on=_string_tuple(payload.get("depends_on", []), f"{prefix}.depends_on"),
            verification=_validate_verification_policy(
                payload.get("verification", "auto"), f"{prefix}.verification"
            ),
        )


@dataclass(frozen=True)
class WorkflowAction:
    steps: Tuple[WorkflowStep, ...]
    type: str = field(default="workflow", init=False)


@dataclass(frozen=True)
class ClarificationAction:
    question: str
    missing_fields: Tuple[str, ...] = ()
    type: str = field(default="clarification", init=False)


@dataclass(frozen=True)
class AbstainAction:
    reason: str
    error_code: str
    recoverable: bool = False
    type: str = field(default="abstain", init=False)


AgentAction = Union[
    DirectAnswerAction,
    ToolCallAction,
    WorkflowAction,
    ClarificationAction,
    AbstainAction,
]


def _parse_action(payload: Mapping[str, Any], registry: ToolRegistry) -> AgentAction:
    action_type = _require_string(payload.get("type"), "action.type")
    if action_type not in ACTION_TYPES:
        raise AgentActionError(f"action.type must be one of {sorted(ACTION_TYPES)}")

    if action_type == "direct_answer":
        return DirectAnswerAction(answer=_require_string(payload.get("answer"), "action.answer"))
    if action_type == "clarification":
        return ClarificationAction(
            question=_require_string(payload.get("question"), "action.question"),
            missing_fields=_string_tuple(payload.get("missing_fields", []), "action.missing_fields"),
        )
    if action_type == "abstain":
        recoverable = payload.get("recoverable", False)
        if not isinstance(recoverable, bool):
            raise AgentActionError("action.recoverable must be a boolean")
        return AbstainAction(
            reason=_require_string(payload.get("reason"), "action.reason"),
            error_code=_require_string(payload.get("error_code"), "action.error_code"),
            recoverable=recoverable,
        )
    if action_type == "tool_call":
        tool_name = _require_string(payload.get("tool"), "action.tool")
        arguments = _require_mapping(payload.get("arguments"), "action.arguments")
        verification = _validate_verification_policy(
            payload.get("verification", "auto"), "action.verification"
        )
        _validate_tool_call(tool_name, arguments, verification, registry, "action")
        return ToolCallAction(tool=tool_name, arguments=arguments, verification=verification)

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise AgentActionError("action.steps must be a non-empty list")
    steps = tuple(
        WorkflowStep.from_dict(_require_mapping(item, f"action.steps[{index}]"), index)
        for index, item in enumerate(raw_steps)
    )
    _validate_workflow(steps, registry)
    return WorkflowAction(steps=steps)


def _validate_workflow(steps: Tuple[WorkflowStep, ...], registry: ToolRegistry) -> None:
    step_ids = [step.step_id for step in steps]
    duplicates = sorted({step_id for step_id in step_ids if step_ids.count(step_id) > 1})
    if duplicates:
        raise AgentActionError(f"action.steps contains duplicate step IDs: {duplicates}")

    step_by_id = {step.step_id: step for step in steps}
    previous_ids = set()
    for index, step in enumerate(steps):
        prefix = f"action.steps[{index}]"
        unknown_dependencies = sorted(set(step.depends_on) - set(step_by_id))
        if unknown_dependencies:
            raise AgentActionError(f"{prefix}.depends_on references unknown steps: {unknown_dependencies}")
        non_previous = sorted(set(step.depends_on) - previous_ids)
        if non_previous:
            raise AgentActionError(f"{prefix}.depends_on must reference earlier steps: {non_previous}")

        _validate_tool_call(step.tool, step.arguments, step.verification, registry, prefix)
        for referenced_step_id, artifact in _find_artifact_references(step.arguments):
            if referenced_step_id not in previous_ids:
                raise AgentActionError(
                    f"{prefix}.arguments references non-previous step {referenced_step_id!r}"
                )
            if referenced_step_id not in step.depends_on:
                raise AgentActionError(
                    f"{prefix}.arguments references {referenced_step_id!r} without declaring it in depends_on"
                )
            producer = registry.get(step_by_id[referenced_step_id].tool)
            if artifact not in producer.output.artifacts:
                raise AgentActionError(
                    f"{prefix}.arguments references unknown artifact {artifact!r} from "
                    f"step {referenced_step_id!r}"
                )
        previous_ids.add(step.step_id)


def _validate_expected_output(
    action: AgentAction,
    expected_output: Optional[ExpectedOutput],
    registry: ToolRegistry,
) -> None:
    if expected_output is None:
        return
    if isinstance(action, (DirectAnswerAction, ClarificationAction, AbstainAction)):
        if expected_output.type != "text":
            raise AgentActionError(
                f"{action.type} can only satisfy expected_output.type 'text'"
            )
        return
    if expected_output.type == "text":
        raise AgentActionError(f"{action.type} does not directly produce text output")

    if isinstance(action, ToolCallAction):
        producing_tools = (registry.get(action.tool),)
    else:
        depended_on = {dependency for step in action.steps for dependency in step.depends_on}
        terminal_steps = [step for step in action.steps if step.step_id not in depended_on]
        producing_tools = tuple(registry.get(step.tool) for step in terminal_steps)

    compatible = any(
        expected_output.type in tool.output.result_types
        and expected_output.coordinate_space == tool.output.coordinate_space
        for tool in producing_tools
    )
    if not compatible:
        names = [tool.name for tool in producing_tools]
        raise AgentActionError(
            "expected_output is incompatible with the action's terminal tool outputs: "
            f"{names}"
        )


@dataclass(frozen=True)
class AgentRequest:
    schema_version: str
    request_id: str
    intent: str
    action: AgentAction
    expected_output: Optional[ExpectedOutput] = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], registry: ToolRegistry) -> "AgentRequest":
        schema_version = _require_string(payload.get("schema_version"), "schema_version")
        if schema_version != "1.0":
            raise AgentActionError(f"Unsupported Agent action schema version {schema_version!r}")
        request_id = _require_string(payload.get("request_id"), "request_id")
        if not IDENTIFIER_PATTERN.fullmatch(request_id):
            raise AgentActionError("request_id has an invalid identifier format")
        expected_payload = payload.get("expected_output")
        expected_output = None
        if expected_payload is not None:
            expected_output = ExpectedOutput.from_dict(
                _require_mapping(expected_payload, "expected_output")
            )
        action = _parse_action(_require_mapping(payload.get("action"), "action"), registry)
        _validate_expected_output(action, expected_output, registry)
        return cls(
            schema_version=schema_version,
            request_id=request_id,
            intent=_require_string(payload.get("intent"), "intent"),
            action=action,
            expected_output=expected_output,
        )


def load_agent_request(path: str | Path, registry: ToolRegistry) -> AgentRequest:
    request_path = Path(path)
    with request_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise AgentActionError(f"Agent request {request_path} must contain an object")
    return AgentRequest.from_dict(payload, registry)
