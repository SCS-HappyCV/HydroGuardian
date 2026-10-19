from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple


HEALTH_STATUSES = {"ready", "not_ready", "disabled", "unavailable"}
EXECUTION_STATUSES = {"succeeded", "failed"}


class ExpertRuntimeError(RuntimeError):
    """Base error raised by the expert runtime layer."""


class ExpertConfigurationError(ExpertRuntimeError):
    """Raised when the expert runtime configuration is invalid."""


class ExpertNotReadyError(ExpertRuntimeError):
    """Raised when an expert is called before it is ready."""


@dataclass(frozen=True)
class ExpertHealth:
    tool: str
    backend: str
    status: str
    initialized: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in HEALTH_STATUSES:
            raise ValueError(f"Unsupported health status {self.status!r}")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExpertHealth":
        return cls(
            tool=str(payload["tool"]),
            backend=str(payload["backend"]),
            status=str(payload["status"]),
            initialized=bool(payload["initialized"]),
            message=str(payload.get("message", "")),
            details=dict(payload.get("details", {})),
        )


@dataclass(frozen=True)
class ExpertError:
    code: str
    message: str
    recoverable: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExpertResult:
    schema_version: str
    invocation_id: str
    tool: str
    tool_version: str
    backend: str
    status: str
    started_at: str
    finished_at: str
    duration_ms: float
    coordinate_space: str
    result_types: Tuple[str, ...]
    artifacts: Dict[str, str]
    manifest_path: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    is_mock: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)
    spatial_context: Dict[str, Any] = field(default_factory=dict)
    warnings: Tuple[str, ...] = ()
    error: Optional[ExpertError] = None

    def __post_init__(self) -> None:
        if self.status not in EXECUTION_STATUSES:
            raise ValueError(f"Unsupported execution status {self.status!r}")
        if self.status == "succeeded" and self.error is not None:
            raise ValueError("A succeeded result cannot contain an error")
        if self.status == "failed" and self.error is None:
            raise ValueError("A failed result must contain an error")

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["result_types"] = list(self.result_types)
        payload["warnings"] = list(self.warnings)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExpertResult":
        error_payload = payload.get("error")
        error = None
        if isinstance(error_payload, Mapping):
            error = ExpertError(
                code=str(error_payload["code"]),
                message=str(error_payload["message"]),
                recoverable=bool(error_payload.get("recoverable", False)),
                details=dict(error_payload.get("details", {})),
            )
        return cls(
            schema_version=str(payload["schema_version"]),
            invocation_id=str(payload["invocation_id"]),
            tool=str(payload["tool"]),
            tool_version=str(payload["tool_version"]),
            backend=str(payload["backend"]),
            status=str(payload["status"]),
            started_at=str(payload["started_at"]),
            finished_at=str(payload["finished_at"]),
            duration_ms=float(payload["duration_ms"]),
            coordinate_space=str(payload["coordinate_space"]),
            result_types=tuple(payload.get("result_types", ())),
            artifacts={str(key): str(value) for key, value in payload.get("artifacts", {}).items()},
            manifest_path=str(payload["manifest_path"]),
            arguments=dict(payload.get("arguments", {})),
            is_mock=bool(payload.get("is_mock", False)),
            metrics=dict(payload.get("metrics", {})),
            spatial_context=dict(payload.get("spatial_context", {})),
            warnings=tuple(str(value) for value in payload.get("warnings", ())),
            error=error,
        )

    def write_manifest(self) -> None:
        manifest = Path(self.manifest_path)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)


def normalize_arguments(arguments: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(arguments, Mapping):
        raise TypeError("Expert arguments must be an object")
    return dict(arguments)
