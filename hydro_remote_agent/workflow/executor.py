from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from hydro_remote_agent.runtime import ExpertRuntime
from hydro_remote_agent.runtime.contracts import ExpertError, ExpertResult
from hydro_remote_agent.schemas.agent_action import (
    REFERENCE_PATTERN,
    AgentRequest,
    WorkflowAction,
    WorkflowStep,
)

from .contracts import WorkflowResult, WorkflowStepResult


EXECUTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
MAX_EXECUTION_ID_LENGTH = 64


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_references(value: Any, results: Mapping[str, WorkflowStepResult]) -> Any:
    if isinstance(value, str):
        match = REFERENCE_PATTERN.fullmatch(value)
        if match is None:
            return value
        step_id = match.group("step")
        artifact = match.group("artifact")
        step_result = results.get(step_id)
        if step_result is None or step_result.status != "succeeded" or step_result.result is None:
            raise ValueError(f"Cannot resolve artifact from unsuccessful step {step_id!r}")
        try:
            return step_result.result.artifacts[artifact]
        except KeyError as exc:
            raise ValueError(f"Step {step_id!r} did not produce artifact {artifact!r}") from exc
    if isinstance(value, dict):
        return {key: _resolve_references(child, results) for key, child in value.items()}
    if isinstance(value, list):
        return [_resolve_references(child, results) for child in value]
    return value


def _verifier_arguments(step: WorkflowStep, result: ExpertResult) -> Dict[str, Any]:
    arguments: Dict[str, Any] = {
        "result_path": result.manifest_path,
        "source_tool": step.tool,
        "result_artifacts": dict(result.artifacts),
    }
    for field_name in ("image_path", "point_cloud_path"):
        value = result.arguments.get(field_name)
        if isinstance(value, str) and value:
            arguments[field_name] = value
    if "image_path" not in arguments:
        after_image = result.arguments.get("after_image_path")
        if isinstance(after_image, str) and after_image:
            arguments["image_path"] = after_image
    return arguments


class WorkflowExecutor:
    """Execute validated workflows through an ExpertRuntime."""

    def __init__(self, runtime: ExpertRuntime, work_dir: str | Path) -> None:
        self.runtime = runtime
        self.registry = runtime.registry
        self.work_dir = Path(work_dir).resolve()

    def execute(
        self,
        request: AgentRequest,
        execution_id: Optional[str] = None,
    ) -> WorkflowResult:
        if not isinstance(request.action, WorkflowAction):
            raise TypeError("WorkflowExecutor only accepts requests with action.type 'workflow'")
        resolved_execution_id = execution_id or f"workflow_{uuid.uuid4().hex}"
        if (
            not EXECUTION_ID_PATTERN.fullmatch(resolved_execution_id)
            or len(resolved_execution_id) > MAX_EXECUTION_ID_LENGTH
        ):
            raise ValueError("execution_id must be path-safe and contain at most 64 characters")
        execution_dir = self.work_dir / resolved_execution_id
        execution_dir.mkdir(parents=True, exist_ok=False)

        started_at = _utc_now()
        started = time.perf_counter()
        step_results: Dict[str, WorkflowStepResult] = {}
        required_tools = self._required_tools(request.action.steps)
        for tool_name in required_tools:
            self.runtime.prepare(tool_name)

        for step in request.action.steps:
            resolved_arguments: Dict[str, Any] = {}
            failed_dependencies = [
                dependency
                for dependency in step.depends_on
                if step_results[dependency].status != "succeeded"
            ]
            if failed_dependencies:
                step_results[step.step_id] = WorkflowStepResult(
                    step_id=step.step_id,
                    tool=step.tool,
                    status="skipped",
                    resolved_arguments={},
                    error=ExpertError(
                        code="dependency_failed",
                        message=f"Dependencies did not succeed: {failed_dependencies}",
                        recoverable=False,
                        details={"dependencies": failed_dependencies},
                    ),
                )
                continue
            try:
                resolved_arguments = _resolve_references(step.arguments, step_results)
                result = self.runtime.invoke(
                    step.tool,
                    resolved_arguments,
                    invocation_id=f"{resolved_execution_id}_{step.step_id}",
                )
                if result.status != "succeeded":
                    message = result.error.message if result.error is not None else "Unknown failure"
                    raise RuntimeError(f"Expert {step.tool!r} failed: {message}")
                verification_result = self._verify_step(
                    resolved_execution_id,
                    step,
                    result,
                )
                step_results[step.step_id] = WorkflowStepResult(
                    step_id=step.step_id,
                    tool=step.tool,
                    status="succeeded",
                    resolved_arguments=resolved_arguments,
                    result=result,
                    verification_result=verification_result,
                )
            except Exception as exc:
                step_results[step.step_id] = WorkflowStepResult(
                    step_id=step.step_id,
                    tool=step.tool,
                    status="failed",
                    resolved_arguments=resolved_arguments,
                    error=ExpertError(
                        code="step_execution_failed",
                        message=f"{type(exc).__name__}: {exc}",
                        recoverable=False,
                    ),
                )

        ordered_results = tuple(step_results[step.step_id] for step in request.action.steps)
        failed = any(step.status != "succeeded" for step in ordered_results)
        terminal_artifacts = self._terminal_artifacts(request.action.steps, step_results)
        warning_messages = {
            warning
            for step in ordered_results
            if step.verification_result is not None
            for warning in step.verification_result.warnings
        }
        if any(
            (step.result is not None and step.result.is_mock)
            or (step.verification_result is not None and step.verification_result.is_mock)
            for step in ordered_results
        ):
            warning_messages.add(
                "Workflow contains mock expert outputs; it is not a real prediction."
            )
        warnings = tuple(sorted(warning_messages))
        manifest_path = execution_dir / "workflow_manifest.json"
        workflow_result = WorkflowResult(
            schema_version="1.0",
            execution_id=resolved_execution_id,
            request_id=request.request_id,
            intent=request.intent,
            status="failed" if failed else "succeeded",
            started_at=started_at,
            finished_at=_utc_now(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
            steps=ordered_results,
            terminal_artifacts=terminal_artifacts,
            manifest_path=str(manifest_path.resolve()),
            is_mock=any(
                step.result is not None and step.result.is_mock for step in ordered_results
            ),
            warnings=warnings,
        )
        workflow_result.write_manifest()
        return workflow_result

    def _required_tools(self, steps: Tuple[WorkflowStep, ...]) -> Tuple[str, ...]:
        names = []
        for step in steps:
            if step.tool not in names:
                names.append(step.tool)
            tool = self.registry.get(step.tool)
            if step.verification != "skip" and tool.verifier and tool.verifier not in names:
                names.append(tool.verifier)
        return tuple(names)

    def _verify_step(
        self,
        execution_id: str,
        step: WorkflowStep,
        result: ExpertResult,
    ) -> Optional[ExpertResult]:
        tool = self.registry.get(step.tool)
        if step.verification == "skip" or tool.verifier is None:
            return None
        verification_result = self.runtime.invoke(
            tool.verifier,
            _verifier_arguments(step, result),
            invocation_id=f"{execution_id}_{step.step_id}_verify",
        )
        if verification_result.status != "succeeded":
            message = (
                verification_result.error.message
                if verification_result.error is not None
                else "Unknown failure"
            )
            raise RuntimeError(f"Verifier {tool.verifier!r} failed: {message}")
        return verification_result

    @staticmethod
    def _terminal_artifacts(
        steps: Tuple[WorkflowStep, ...],
        results: Mapping[str, WorkflowStepResult],
    ) -> Dict[str, str]:
        depended_on = {dependency for step in steps for dependency in step.depends_on}
        terminal = [step for step in steps if step.step_id not in depended_on]
        artifacts: Dict[str, str] = {}
        for step in terminal:
            result = results[step.step_id]
            if result.status == "succeeded" and result.result is not None:
                for name, path in result.result.artifacts.items():
                    key = name if len(terminal) == 1 else f"{step.step_id}.{name}"
                    artifacts[key] = path
        return artifacts
