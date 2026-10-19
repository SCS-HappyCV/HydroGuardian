from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


JOB_STATUSES = {
    "queued_planning",
    "planning",
    "queued_execution",
    "executing",
    "succeeded",
    "blocked_expert",
    "failed",
    "cancelled",
}
TERMINAL_JOB_STATUSES = {"succeeded", "blocked_expert", "failed", "cancelled"}
STEP_STATUSES = {"pending", "dispatched", "running", "succeeded", "failed", "lost", "cancelled"}


@dataclass(frozen=True)
class JobSubmission:
    request_id: str
    query: str
    assets: Dict[str, str]
    language: str = "auto"
    planned_request: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "JobSubmission":
        request_id = str(payload.get("request_id", "")).strip()
        query = str(payload.get("query", "")).strip()
        language = str(payload.get("language", "auto")).strip() or "auto"
        assets_value = payload.get("assets", {})
        if not request_id:
            raise ValueError("request_id must be a non-empty string")
        if not query:
            raise ValueError("query must be a non-empty string")
        if not isinstance(assets_value, dict):
            raise ValueError("assets must be an object")
        assets: Dict[str, str] = {}
        for name, value in assets_value.items():
            if not isinstance(name, str) or not isinstance(value, str) or not value.strip():
                raise ValueError("assets must map string names to non-empty paths")
            assets[name] = value.strip()
        planned = payload.get("planned_request")
        if planned is not None and not isinstance(planned, dict):
            raise ValueError("planned_request must be an object when supplied")
        return cls(
            request_id=request_id,
            query=query,
            assets=assets,
            language=language,
            planned_request=dict(planned) if isinstance(planned, dict) else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "query": self.query,
            "assets": dict(self.assets),
            "language": self.language,
            "planned_request": self.planned_request,
        }


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    request_id: str
    trace_id: str
    status: str
    submission: Dict[str, Any]
    plan: Optional[Dict[str, Any]]
    result: Optional[Dict[str, Any]]
    error: Optional[Dict[str, Any]]
    attempts: int
    lease_owner: Optional[str]
    lease_expires_at: Optional[float]
    created_at: str
    updated_at: str
    version: int

    def __post_init__(self) -> None:
        if self.status not in JOB_STATUSES:
            raise ValueError(f"Unsupported job status {self.status!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "status": self.status,
            "submission": self.submission,
            "plan": self.plan,
            "result": self.result,
            "error": self.error,
            "attempts": self.attempts,
            "lease_owner": self.lease_owner,
            "lease_expires_at": self.lease_expires_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
        }


@dataclass(frozen=True)
class StepRecord:
    step_id: str
    job_id: str
    tool: str
    status: str
    attempt: int = 1
    worker_id: Optional[str] = None
    progress: float = 0.0
    phase: str = ""
    arguments: Dict[str, Any] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    updated_at: str = ""

    def __post_init__(self) -> None:
        if self.status not in STEP_STATUSES:
            raise ValueError(f"Unsupported step status {self.status!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id, "job_id": self.job_id, "tool": self.tool,
            "status": self.status, "attempt": self.attempt, "worker_id": self.worker_id,
            "progress": self.progress, "phase": self.phase, "arguments": self.arguments or {},
            "result": self.result, "error": self.error, "updated_at": self.updated_at,
        }
