from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping

from hydro_remote_agent.schemas.tool_spec import ToolSpec

from .contracts import ExpertHealth, ExpertResult


class ExpertAdapter(ABC):
    """Lifecycle and inference boundary implemented by every expert backend."""

    def __init__(
        self,
        tool_spec: ToolSpec,
        work_dir: str | Path,
        backend: str,
        enabled: bool = True,
    ) -> None:
        self.tool_spec = tool_spec
        self.work_dir = Path(work_dir)
        self.backend = backend
        self.enabled = enabled

    @abstractmethod
    def prepare(self) -> ExpertHealth:
        """Load resources and make the expert ready for prediction."""

    @abstractmethod
    def health_check(self) -> ExpertHealth:
        """Return current readiness without performing inference."""

    @abstractmethod
    def predict(self, invocation_id: str, arguments: Mapping[str, Any]) -> ExpertResult:
        """Run one validated expert invocation."""

    @abstractmethod
    def shutdown(self) -> None:
        """Release model and device resources."""
