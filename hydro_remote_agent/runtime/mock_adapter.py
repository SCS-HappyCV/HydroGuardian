from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping

from .adapter import ExpertAdapter
from .contracts import ExpertHealth, ExpertNotReadyError, ExpertResult, normalize_arguments


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MockExpertAdapter(ExpertAdapter):
    """Contract-complete placeholder used until a real expert is connected."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, backend="mock", **kwargs)
        self._initialized = False

    def prepare(self) -> ExpertHealth:
        if not self.enabled:
            return self.health_check()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True
        return self.health_check()

    def health_check(self) -> ExpertHealth:
        if not self.enabled:
            return ExpertHealth(
                tool=self.tool_spec.name,
                backend=self.backend,
                status="disabled",
                initialized=False,
                message="Expert is disabled by runtime configuration.",
            )
        return ExpertHealth(
            tool=self.tool_spec.name,
            backend=self.backend,
            status="ready" if self._initialized else "not_ready",
            initialized=self._initialized,
            message=(
                "Mock adapter is ready; outputs are placeholders, not model predictions."
                if self._initialized
                else "Mock adapter has not been prepared."
            ),
            details={"is_mock": True},
        )

    def predict(self, invocation_id: str, arguments: Mapping[str, Any]) -> ExpertResult:
        if not self.enabled or not self._initialized:
            raise ExpertNotReadyError(f"Expert {self.tool_spec.name!r} is not ready")
        normalized_arguments = normalize_arguments(arguments)
        started_at = _utc_now()
        started = time.perf_counter()
        invocation_dir = self.work_dir / invocation_id
        invocation_dir.mkdir(parents=True, exist_ok=False)

        artifacts: Dict[str, str] = {}
        for artifact_name in self.tool_spec.output.artifacts:
            artifact_path = invocation_dir / f"{artifact_name}.mock.json"
            payload = {
                "schema_version": "1.0",
                "tool": self.tool_spec.name,
                "artifact": artifact_name,
                "backend": self.backend,
                "is_mock": True,
                "usable_as_prediction": False,
                "arguments": normalized_arguments,
            }
            with artifact_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            artifacts[artifact_name] = str(artifact_path.resolve())

        manifest_path = invocation_dir / "manifest.json"
        result = ExpertResult(
            schema_version="1.0",
            invocation_id=invocation_id,
            tool=self.tool_spec.name,
            tool_version=self.tool_spec.version,
            backend=self.backend,
            status="succeeded",
            started_at=started_at,
            finished_at=_utc_now(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
            coordinate_space=self.tool_spec.output.coordinate_space,
            result_types=self.tool_spec.output.result_types,
            artifacts=artifacts,
            manifest_path=str(manifest_path.resolve()),
            arguments=normalized_arguments,
            is_mock=True,
            warnings=("Mock output: no expert model was executed.",),
        )
        result.write_manifest()
        return result

    def shutdown(self) -> None:
        self._initialized = False
