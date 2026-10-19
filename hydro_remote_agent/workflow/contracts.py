from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from hydro_remote_agent.runtime.contracts import ExpertError, ExpertResult


WORKFLOW_STATUSES = {"succeeded", "failed"}
STEP_STATUSES = {"succeeded", "failed", "skipped"}
AGENT_EXECUTION_STATUSES = {"succeeded", "failed", "skipped"}
AGENT_EXECUTION_MODES = {"planner_only", "expert_runtime", "skipped_mock"}
AGENT_EXECUTION_OUTCOMES = {
    "result",
    "response",
    "no_target",
    "no_reference",
    "execution_failed",
    "skipped_mock",
}


@dataclass(frozen=True)
class WorkflowStepResult:
    step_id: str
    tool: str
    status: str
    resolved_arguments: Dict[str, Any]
    result: Optional[ExpertResult] = None
    verification_result: Optional[ExpertResult] = None
    error: Optional[ExpertError] = None

    def __post_init__(self) -> None:
        if self.status not in STEP_STATUSES:
            raise ValueError(f"Unsupported workflow step status {self.status!r}")
        if self.status == "succeeded" and (self.result is None or self.error is not None):
            raise ValueError("A succeeded workflow step requires a result and no error")
        if self.status != "succeeded" and self.error is None:
            raise ValueError("A failed or skipped workflow step requires an error")


@dataclass(frozen=True)
class WorkflowResult:
    schema_version: str
    execution_id: str
    request_id: str
    intent: str
    status: str
    started_at: str
    finished_at: str
    duration_ms: float
    steps: Tuple[WorkflowStepResult, ...]
    terminal_artifacts: Dict[str, str]
    manifest_path: str
    is_mock: bool = False
    warnings: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status not in WORKFLOW_STATUSES:
            raise ValueError(f"Unsupported workflow status {self.status!r}")

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return payload

    def write_manifest(self) -> None:
        manifest = Path(self.manifest_path)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)


@dataclass(frozen=True)
class AgentExecutionResult:
    schema_version: str
    execution_id: str
    request_id: str
    intent: str
    action_type: str
    status: str
    execution_mode: str
    outcome: str
    started_at: str
    finished_at: str
    duration_ms: float
    required_tools: Tuple[str, ...]
    manifest_path: str
    response: Optional[str] = None
    workflow_result: Optional[WorkflowResult] = None
    error: Optional[ExpertError] = None
    is_mock: bool = False
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    risk_candidates: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status not in AGENT_EXECUTION_STATUSES:
            raise ValueError(f"Unsupported Agent execution status {self.status!r}")
        if self.execution_mode not in AGENT_EXECUTION_MODES:
            raise ValueError(f"Unsupported Agent execution mode {self.execution_mode!r}")
        if self.outcome not in AGENT_EXECUTION_OUTCOMES:
            raise ValueError(f"Unsupported Agent execution outcome {self.outcome!r}")
        if self.status == "succeeded" and self.error is not None:
            raise ValueError("A succeeded Agent execution cannot contain an error")
        if self.status != "succeeded" and self.error is None:
            raise ValueError("A failed or skipped Agent execution requires an error")

    @property
    def terminal_artifacts(self) -> Dict[str, str]:
        if self.workflow_result is None:
            return {}
        return dict(self.workflow_result.terminal_artifacts)

    @property
    def spatial_context(self) -> Dict[str, Any]:
        if self.workflow_result is None:
            return {}
        assets: Dict[str, Any] = {}
        primary = None
        for step in self.workflow_result.steps:
            for result in (step.result, step.verification_result):
                if result is None or not result.spatial_context:
                    continue
                context_assets = result.spatial_context.get("assets", {})
                if isinstance(context_assets, dict):
                    assets.update(context_assets)
                if primary is None and isinstance(result.spatial_context.get("primary"), dict):
                    primary = result.spatial_context["primary"]
        if not assets and primary is None:
            return {}
        return {
            "schema_version": "hydro-spatial-context.v1",
            "assets": assets,
            "primary": primary or next(iter(assets.values()), None),
        }

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["required_tools"] = list(self.required_tools)
        payload["warnings"] = list(self.warnings)
        payload["terminal_artifacts"] = self.terminal_artifacts
        payload["risk_candidates"] = [dict(candidate) for candidate in self.risk_candidates]
        payload["spatial_context"] = self.spatial_context
        return payload

    def write_manifest(self) -> None:
        manifest = Path(self.manifest_path)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
