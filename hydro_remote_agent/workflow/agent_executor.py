from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from hydro_remote_agent.runtime import ExpertRuntime
from hydro_remote_agent.runtime.contracts import ExpertError
from hydro_remote_agent.schemas.agent_action import (
    AbstainAction,
    AgentRequest,
    ClarificationAction,
    DirectAnswerAction,
    ToolCallAction,
    WorkflowAction,
    WorkflowStep,
)

from .contracts import AgentExecutionResult
from .executor import MAX_EXECUTION_ID_LENGTH, WorkflowExecutor
from .risk_rules import compile_risk_candidates


EXECUTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentExecutor:
    """Execute every valid Agent action while preserving execution provenance."""

    def __init__(self, runtime: ExpertRuntime, work_dir: str | Path) -> None:
        self.runtime = runtime
        self.work_dir = Path(work_dir).resolve()
        self.workflow_executor = WorkflowExecutor(runtime, self.work_dir / "workflows")

    def required_tools(self, request: AgentRequest) -> Tuple[str, ...]:
        action = request.action
        if isinstance(action, ToolCallAction):
            steps = (self._tool_call_step(action),)
        elif isinstance(action, WorkflowAction):
            steps = action.steps
        else:
            return ()
        return self.workflow_executor._required_tools(steps)

    def mock_tools(self, request: AgentRequest) -> Tuple[str, ...]:
        return tuple(
            tool
            for tool in self.required_tools(request)
            if self.runtime.get_adapter(tool).backend == "mock"
        )

    def execute(
        self,
        request: AgentRequest,
        execution_id: Optional[str] = None,
        skip_mock: bool = True,
    ) -> AgentExecutionResult:
        resolved_id = execution_id or f"agent_{uuid.uuid4().hex}"
        if (
            not EXECUTION_ID_PATTERN.fullmatch(resolved_id)
            or len(resolved_id) > MAX_EXECUTION_ID_LENGTH
        ):
            raise ValueError("execution_id must be path-safe and contain at most 64 characters")

        started_at = _utc_now()
        started = time.perf_counter()
        action_type = request.action.type
        required_tools = self.required_tools(request)
        mock_tools = self.mock_tools(request)
        execution_dir = self.work_dir / resolved_id
        execution_dir.mkdir(parents=True, exist_ok=False)
        manifest_path = execution_dir / "agent_execution_manifest.json"

        if mock_tools and skip_mock:
            names = ", ".join(mock_tools)
            result = AgentExecutionResult(
                schema_version="1.0",
                execution_id=resolved_id,
                request_id=request.request_id,
                intent=request.intent,
                action_type=action_type,
                status="skipped",
                execution_mode="skipped_mock",
                outcome="skipped_mock",
                started_at=started_at,
                finished_at=_utc_now(),
                duration_ms=(time.perf_counter() - started) * 1000.0,
                required_tools=required_tools,
                manifest_path=str(manifest_path.resolve()),
                error=ExpertError(
                    code="mock_expert_required",
                    message=f"Execution requires mock expert(s): {names}",
                    recoverable=True,
                    details={"mock_tools": list(mock_tools)},
                ),
                warnings=("No expert inference was executed for this request.",),
            )
            result.write_manifest()
            return result

        response = self._planner_response(request)
        if response is not None:
            result = AgentExecutionResult(
                schema_version="1.0",
                execution_id=resolved_id,
                request_id=request.request_id,
                intent=request.intent,
                action_type=action_type,
                status="succeeded",
                execution_mode="planner_only",
                outcome="response",
                started_at=started_at,
                finished_at=_utc_now(),
                duration_ms=(time.perf_counter() - started) * 1000.0,
                required_tools=(),
                manifest_path=str(manifest_path.resolve()),
                response=response,
            )
            result.write_manifest()
            return result

        workflow_request = self._workflow_request(request)
        workflow_result = self.workflow_executor.execute(
            workflow_request,
            execution_id=resolved_id,
        )
        workflow_error = self._workflow_error(workflow_result)
        result = AgentExecutionResult(
            schema_version="1.0",
            execution_id=resolved_id,
            request_id=request.request_id,
            intent=request.intent,
            action_type=action_type,
            status=workflow_result.status,
            execution_mode="expert_runtime",
            outcome=self._workflow_outcome(workflow_result),
            started_at=started_at,
            finished_at=_utc_now(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
            required_tools=required_tools,
            manifest_path=str(manifest_path.resolve()),
            workflow_result=workflow_result,
            error=(
                None
                if workflow_result.status == "succeeded"
                else workflow_error
            ),
            is_mock=workflow_result.is_mock,
            warnings=workflow_result.warnings,
            risk_candidates=tuple(
                candidate.to_dict()
                for candidate in compile_risk_candidates(workflow_result)
            ),
        )
        result.write_manifest()
        return result

    @staticmethod
    def _workflow_error(workflow_result) -> ExpertError:
        failed_step = next(
            (step for step in workflow_result.steps if step.status == "failed" and step.error is not None),
            None,
        )
        if failed_step is None:
            return ExpertError(
                code="workflow_failed",
                message="One or more expert workflow steps failed.",
                recoverable=False,
            )
        return ExpertError(
            code=failed_step.error.code,
            message=failed_step.error.message,
            recoverable=failed_step.error.recoverable,
            details={
                **failed_step.error.details,
                "step_id": failed_step.step_id,
                "tool": failed_step.tool,
            },
        )

    @staticmethod
    def _tool_call_step(action: ToolCallAction) -> WorkflowStep:
        return WorkflowStep(
            step_id="invoke",
            tool=action.tool,
            arguments=action.arguments,
            verification=action.verification,
        )

    def _workflow_request(self, request: AgentRequest) -> AgentRequest:
        if isinstance(request.action, WorkflowAction):
            return request
        if not isinstance(request.action, ToolCallAction):
            raise TypeError(f"Action {request.action.type!r} does not invoke experts")
        return AgentRequest(
            schema_version=request.schema_version,
            request_id=request.request_id,
            intent=request.intent,
            action=WorkflowAction(steps=(self._tool_call_step(request.action),)),
            expected_output=request.expected_output,
        )

    @staticmethod
    def _planner_response(request: AgentRequest) -> Optional[str]:
        action = request.action
        if isinstance(action, DirectAnswerAction):
            return action.answer
        if isinstance(action, ClarificationAction):
            return action.question
        if isinstance(action, AbstainAction):
            return action.reason
        return None

    @staticmethod
    def _workflow_outcome(workflow_result) -> str:
        if workflow_result.status != "succeeded":
            return "execution_failed"
        outcomes = [
            step.result.metrics.get("outcome")
            for step in workflow_result.steps
            if step.status == "succeeded" and step.result is not None
        ]
        for outcome in reversed(outcomes):
            if outcome in {"no_target", "no_reference"}:
                return str(outcome)
        return "result"
