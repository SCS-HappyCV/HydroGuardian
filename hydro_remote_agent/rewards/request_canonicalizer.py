from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence

from hydro_remote_agent.schemas.agent_action import AgentActionError, AgentRequest
from hydro_remote_agent.schemas.tool_spec import ToolRegistry


ARTIFACT_REFERENCE_PATTERN = re.compile(
    r"^\$\{(?P<step>[A-Za-z][A-Za-z0-9_-]*)\.artifacts\.(?P<artifact>[A-Za-z][A-Za-z0-9_]*)\}$"
)
ORDER_INSENSITIVE_LIST_FIELDS = {
    "class_ids",
    "labels",
    "missing_fields",
    "relation_predicates",
    "spatial_relation_predicates",
    "target_class_ids",
}


def _canonical_json_value(value: Any, field_name: Optional[str] = None) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json_value(value[key], str(key))
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        normalized = [_canonical_json_value(item) for item in value]
        if field_name in ORDER_INSENSITIVE_LIST_FIELDS:
            return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False))
        return normalized
    if isinstance(value, float) and value == 0.0:
        return 0.0
    return value


def _find_artifact_references(value: Any) -> tuple[tuple[str, str], ...]:
    references: list[tuple[str, str]] = []
    if isinstance(value, str):
        match = ARTIFACT_REFERENCE_PATTERN.fullmatch(value)
        if match:
            references.append((match.group("step"), match.group("artifact")))
    elif isinstance(value, Mapping):
        for child in value.values():
            references.extend(_find_artifact_references(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            references.extend(_find_artifact_references(child))
    return tuple(sorted(set(references)))


def _payload(value: str | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    if not isinstance(parsed, Mapping):
        raise ValueError("AgentRequest must be a JSON object")
    return parsed


@dataclass(frozen=True)
class CanonicalAgentRequest:
    valid: bool
    error: Optional[str]
    schema_version: Optional[str]
    request_id: Optional[str]
    intent: Optional[str]
    action_type: Optional[str]
    tools: tuple[str, ...]
    arguments: tuple[tuple[str, Any], ...]
    workflow_nodes: tuple[tuple[str, str], ...]
    workflow_edges: tuple[tuple[str, str], ...]
    artifact_references: tuple[tuple[str, str, str], ...]
    verification_policies: tuple[tuple[str, str], ...]
    stop_fields: tuple[tuple[str, Any], ...]
    expected_output: tuple[tuple[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _invalid(error: Exception) -> CanonicalAgentRequest:
    return CanonicalAgentRequest(
        valid=False,
        error=f"{type(error).__name__}: {error}",
        schema_version=None,
        request_id=None,
        intent=None,
        action_type=None,
        tools=(),
        arguments=(),
        workflow_nodes=(),
        workflow_edges=(),
        artifact_references=(),
        verification_policies=(),
        stop_fields=(),
        expected_output=(),
    )


def canonicalize_agent_request(
    value: str | Mapping[str, Any],
    registry: ToolRegistry,
) -> CanonicalAgentRequest:
    try:
        raw = _payload(value)
        request = AgentRequest.from_dict(raw, registry)
    except (json.JSONDecodeError, ValueError, TypeError, AgentActionError) as exc:
        return _invalid(exc)

    action = raw["action"]
    action_type = request.action.type
    tools: list[str] = []
    arguments: list[tuple[str, Any]] = []
    workflow_nodes: list[tuple[str, str]] = []
    workflow_edges: list[tuple[str, str]] = []
    artifact_references: list[tuple[str, str, str]] = []
    verification_policies: list[tuple[str, str]] = []

    if action_type == "tool_call":
        tool = str(action["tool"])
        tools.append(tool)
        arguments.append((tool, _canonical_json_value(action.get("arguments", {}))))
        verification_policies.append((tool, str(action.get("verification", "auto"))))
    elif action_type == "workflow":
        for step in action["steps"]:
            step_id = str(step["step_id"])
            tool = str(step["tool"])
            tools.append(tool)
            workflow_nodes.append((step_id, tool))
            arguments.append((step_id, _canonical_json_value(step.get("arguments", {}))))
            verification_policies.append((step_id, str(step.get("verification", "auto"))))
            workflow_edges.extend((str(dependency), step_id) for dependency in step.get("depends_on", []))
            artifact_references.extend(
                (step_id, producer, artifact)
                for producer, artifact in _find_artifact_references(step.get("arguments", {}))
            )

    stop_payload: dict[str, Any] = {}
    if action_type == "direct_answer":
        stop_payload["answer"] = action.get("answer")
    elif action_type == "clarification":
        stop_payload["question"] = action.get("question")
        stop_payload["missing_fields"] = action.get("missing_fields", [])
    elif action_type == "abstain":
        stop_payload["reason"] = action.get("reason")
        stop_payload["error_code"] = action.get("error_code")
        stop_payload["recoverable"] = action.get("recoverable", False)

    expected_output = raw.get("expected_output") or {}
    return CanonicalAgentRequest(
        valid=True,
        error=None,
        schema_version=request.schema_version,
        request_id=request.request_id,
        intent=request.intent,
        action_type=action_type,
        tools=tuple(sorted(tools)),
        arguments=tuple(sorted(arguments, key=lambda item: item[0])),
        workflow_nodes=tuple(sorted(workflow_nodes)),
        workflow_edges=tuple(sorted(set(workflow_edges))),
        artifact_references=tuple(sorted(set(artifact_references))),
        verification_policies=tuple(sorted(verification_policies)),
        stop_fields=tuple(sorted(_canonical_json_value(stop_payload).items())),
        expected_output=tuple(sorted(_canonical_json_value(expected_output).items())),
    )
