from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, Optional

from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import ToolRegistry
from hydro_remote_agent.workflow import AgentExecutor

from .store import JobStore
from .infra import NullEventBus, event_payload
from .workflow_patches import WorkflowPatchStore

if TYPE_CHECKING:
    from .planner import PlannerBackend


def _error(code: str, exc: Exception, recoverable: bool = False) -> Dict[str, Any]:
    return {
        "code": code,
        "message": f"{type(exc).__name__}: {exc}",
        "recoverable": recoverable,
    }


def _execution_attempt(store: JobStore, job_id: str) -> int:
    retries = sum(
        event.get("event_type") == "execution_retry"
        for event in store.events(job_id)
    )
    return retries + 1


def _is_transient_expert_error(exc: Exception) -> bool:
    message = f"{type(exc).__name__}: {exc}".lower()
    return any(
        marker in message
        for marker in (
            "no online worker supports",
            "worker_disconnected",
            "worker disconnected",
            "keepalive ping timeout",
            "connection reset",
            "connection refused",
            "http 503",
        )
    )


def _patch_plan(job: Any, patch: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "request_id": job.request_id,
        "intent": "runtime_workflow_patch",
        "action": {
            "type": "tool_call", "tool": patch["tool"],
            "arguments": patch["arguments"], "verification": patch["verification"],
        },
        "expected_output": None,
    }


def _merge_job_results(previous: Optional[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    if not previous:
        return current
    previous_batches = previous.get("execution_batches")
    batches = list(previous_batches) if isinstance(previous_batches, list) else [dict(previous)]
    batches.append(dict(current))
    merged = dict(current)
    merged["execution_batches"] = batches
    prior_artifacts = previous.get("terminal_artifacts") if isinstance(previous.get("terminal_artifacts"), dict) else {}
    next_artifacts = current.get("terminal_artifacts") if isinstance(current.get("terminal_artifacts"), dict) else {}
    merged["terminal_artifacts"] = {**prior_artifacts, **next_artifacts}
    prior_candidates = previous.get("risk_candidates") if isinstance(previous.get("risk_candidates"), list) else []
    next_candidates = current.get("risk_candidates") if isinstance(current.get("risk_candidates"), list) else []
    merged["risk_candidates"] = [*prior_candidates, *next_candidates]
    prior_workflow = previous.get("workflow_result") if isinstance(previous.get("workflow_result"), dict) else None
    next_workflow = current.get("workflow_result") if isinstance(current.get("workflow_result"), dict) else None
    if prior_workflow and next_workflow:
        merged["workflow_result"] = {
            **next_workflow,
            "steps": [*(prior_workflow.get("steps") or []), *(next_workflow.get("steps") or [])],
            "terminal_artifacts": {**(prior_workflow.get("terminal_artifacts") or {}), **(next_workflow.get("terminal_artifacts") or {})},
        }
    return merged


class PlannerWorker:
    def __init__(
        self,
        store: JobStore,
        backend: PlannerBackend,
        registry: ToolRegistry,
        worker_id: Optional[str] = None,
        lease_seconds: float = 1800.0,
        event_bus: Any = None,
    ) -> None:
        self.store = store
        self.backend = backend
        self.registry = registry
        self.worker_id = worker_id or f"planner_{uuid.uuid4().hex[:12]}"
        self.lease_seconds = lease_seconds
        self.event_bus = event_bus or NullEventBus()

    def _publish_latest(self, job_id: str) -> None:
        try:
            self.event_bus.publish(event_payload(job_id, self.store.events(job_id)[-1]))
        except Exception:
            return None

    def run_once(self) -> bool:
        self.store.recover_expired()
        job = self.store.claim("planning", self.worker_id, self.lease_seconds)
        if job is None:
            return False
        print(f"PLANNER_JOB_CLAIMED job_id={job.job_id} trace_id={job.trace_id}", flush=True)
        try:
            plan = self.backend.plan(job.submission)
            request = AgentRequest.from_dict(plan, self.registry)
            if request.request_id != job.request_id:
                raise ValueError("Planner output request_id does not match the job")
            self.store.transition(
                job.job_id,
                "planning",
                "queued_execution",
                plan=plan,
                event_type="planning_succeeded",
            )
            self._publish_latest(job.job_id)
            print(f"PLANNER_JOB_SUCCEEDED job_id={job.job_id}", flush=True)
        except Exception as exc:
            self.store.transition(
                job.job_id,
                "planning",
                "failed",
                error=_error("planning_failed", exc),
                event_type="planning_failed",
            )
            self._publish_latest(job.job_id)
            print(f"PLANNER_JOB_FAILED job_id={job.job_id} error={type(exc).__name__}: {exc}", flush=True)
        return True


class ExecutorWorker:
    def __init__(
        self,
        store: JobStore,
        executor: AgentExecutor,
        registry: ToolRegistry,
        worker_id: Optional[str] = None,
        lease_seconds: float = 3600.0,
        event_bus: Any = None,
        max_attempts: int = 3,
        transient_retry_delay_seconds: float = 15.0,
    ) -> None:
        self.store = store
        self.executor = executor
        self.registry = registry
        self.worker_id = worker_id or f"executor_{uuid.uuid4().hex[:12]}"
        self.lease_seconds = lease_seconds
        self.event_bus = event_bus or NullEventBus()
        self.max_attempts = max(1, int(max_attempts))
        self.transient_retry_delay_seconds = max(
            0.0, float(transient_retry_delay_seconds)
        )
        self.workflow_patches = WorkflowPatchStore(store)

    def _publish_latest(self, job_id: str) -> None:
        try:
            self.event_bus.publish(event_payload(job_id, self.store.events(job_id)[-1]))
        except Exception:
            return None

    def run_once(self) -> bool:
        self.store.recover_expired()
        job = self.store.claim("execution", self.worker_id, self.lease_seconds)
        if job is None:
            return False
        print(f"EXECUTOR_JOB_CLAIMED job_id={job.job_id} trace_id={job.trace_id}", flush=True)
        patch: Optional[Dict[str, Any]] = None
        try:
            if job.plan is None:
                raise ValueError("Execution job has no validated plan")
            if job.result is not None:
                patch = self.workflow_patches.claim(job.job_id, self.worker_id)
            request = AgentRequest.from_dict(_patch_plan(job, patch) if patch else job.plan, self.registry)
            mock_tools = self.executor.mock_tools(request)
            if mock_tools:
                self.store.transition(
                    job.job_id,
                    "executing",
                    "blocked_expert",
                    error={
                        "code": "expert_not_deployed",
                        "message": "Required expert is not deployed.",
                        "recoverable": True,
                        "tools": list(mock_tools),
                    },
                    event_type="execution_blocked",
                )
                self._publish_latest(job.job_id)
                print(
                    f"EXECUTOR_JOB_BLOCKED job_id={job.job_id} tools={','.join(mock_tools)}",
                    flush=True,
                )
                return True
            execution_attempt = _execution_attempt(self.store, job.job_id)
            execution_id = patch["step_id"].removesuffix("_invoke") if patch else f"{job.job_id}_a{execution_attempt}"
            result = self.executor.execute(
                request,
                execution_id=execution_id,
                skip_mock=True,
            )
            result_payload = result.to_dict()
            merged_result = _merge_job_results(job.result, result_payload)
            final_status = "succeeded" if result.status == "succeeded" else "failed"
            if patch and final_status == "succeeded":
                self.workflow_patches.complete(patch["patch_id"], result_payload)
                self.store.record_event(job.job_id, "workflow_patch_succeeded", {
                    "patch_id": patch["patch_id"], "step_id": patch["step_id"], "tool": patch["tool"],
                })
            elif patch:
                self.workflow_patches.fail(
                    patch["patch_id"],
                    result_payload.get("error") or {"code": "workflow_patch_failed", "message": "新增专家步骤执行失败"},
                )
                self.store.record_event(job.job_id, "workflow_patch_failed", {
                    "patch_id": patch["patch_id"], "step_id": patch["step_id"], "tool": patch["tool"],
                })
                self.store.transition(
                    job.job_id, "executing", "succeeded", result=job.result,
                    event_type="workflow_patch_failed",
                )
                self._publish_latest(job.job_id)
                return True
            if final_status == "failed" and execution_attempt < self.max_attempts:
                self.store.transition(
                    job.job_id,
                    "executing",
                    "queued_execution",
                    error={"code": "execution_retry", "attempt": execution_attempt, "max_attempts": self.max_attempts},
                    event_type="execution_retry",
                )
                self._publish_latest(job.job_id)
                return True
            if final_status == "succeeded" and self.workflow_patches.has_queued(job.job_id):
                self.store.transition(
                    job.job_id, "executing", "queued_execution", result=merged_result,
                    event_type="execution_batch_succeeded",
                )
                self._publish_latest(job.job_id)
                return True
            self.store.transition(
                job.job_id,
                "executing",
                final_status,
                result=merged_result,
                error=result_payload.get("error") if final_status == "failed" else None,
                event_type="execution_succeeded" if final_status == "succeeded" else "execution_failed",
            )
            self._publish_latest(job.job_id)
            print(
                f"EXECUTOR_JOB_{final_status.upper()} job_id={job.job_id} "
                f"outcome={result.outcome}",
                flush=True,
            )
            self.workflow_patches.ensure_queued_execution(job.job_id)
        except Exception as exc:
            if patch is not None:
                try:
                    error = _error("workflow_patch_failed", exc)
                    self.workflow_patches.fail(patch["patch_id"], error)
                    self.store.record_event(job.job_id, "workflow_patch_failed", {
                        "patch_id": patch["patch_id"], "step_id": patch["step_id"],
                        "tool": patch["tool"], "error": error,
                    })
                    self.store.transition(
                        job.job_id, "executing", "succeeded", result=job.result,
                        event_type="workflow_patch_preserved_previous_result",
                    )
                    self._publish_latest(job.job_id)
                    return True
                except Exception:
                    pass
            execution_attempt = _execution_attempt(self.store, job.job_id)
            transient = _is_transient_expert_error(exc)
            if transient and execution_attempt < self.max_attempts:
                time.sleep(self.transient_retry_delay_seconds)
            if execution_attempt < self.max_attempts:
                self.store.transition(
                    job.job_id, "executing", "queued_execution",
                    error={
                        **_error("execution_retry", exc, recoverable=True),
                        "attempt": execution_attempt,
                        "max_attempts": self.max_attempts,
                        "retry_delay_seconds": (
                            self.transient_retry_delay_seconds if transient else 0.0
                        ),
                    },
                    event_type="execution_retry",
                )
            else:
                self.store.transition(
                    job.job_id, "executing", "failed",
                    error=_error("execution_failed", exc), event_type="execution_failed",
                )
            self._publish_latest(job.job_id)
            print(f"EXECUTOR_JOB_FAILED job_id={job.job_id} error={type(exc).__name__}: {exc}", flush=True)
        return True


def run_worker_loop(worker: Any, poll_seconds: float = 1.0, once: bool = False) -> None:
    while True:
        handled = worker.run_once()
        if once:
            return
        if not handled:
            time.sleep(max(float(poll_seconds), 0.05))
