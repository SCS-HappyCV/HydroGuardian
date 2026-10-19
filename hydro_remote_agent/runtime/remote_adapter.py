from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from hydro_remote_agent.schemas.tool_spec import ToolSpec

from .adapter import ExpertAdapter
from .contracts import ExpertHealth, ExpertNotReadyError, ExpertResult, ExpertRuntimeError


class RemoteExpertError(ExpertRuntimeError):
    """Raised when the Expert Worker cannot complete a protocol request."""


class RemoteExpertAdapter(ExpertAdapter):
    def __init__(
        self,
        tool_spec: ToolSpec,
        work_dir: str | Path,
        base_url: str,
        timeout_seconds: float = 600.0,
        api_prefix: str = "/v1",
    ) -> None:
        super().__init__(
            tool_spec=tool_spec,
            work_dir=work_dir,
            backend="remote_expert_worker",
            enabled=True,
        )
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(float(timeout_seconds), 1.0)
        self.api_prefix = "/" + api_prefix.strip("/")
        self._health = ExpertHealth(
            tool=tool_spec.name,
            backend=self.backend,
            status="not_ready",
            initialized=False,
            message="Remote expert readiness has not been checked.",
            details={"base_url": self.base_url},
        )

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            response_text = exc.read().decode("utf-8", errors="replace")
            raise RemoteExpertError(
                f"Expert Worker returned HTTP {exc.code} for {path}: {response_text}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RemoteExpertError(f"Expert Worker request failed for {path}: {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RemoteExpertError(f"Expert Worker returned invalid JSON for {path}") from exc
        if not isinstance(result, dict):
            raise RemoteExpertError(f"Expert Worker response for {path} must be an object")
        return result

    @property
    def _tool_path(self) -> str:
        return f"{self.api_prefix}/tools/{quote(self.tool_spec.name, safe='')}"

    def prepare(self) -> ExpertHealth:
        payload = self._request("POST", f"{self._tool_path}/prepare", {})
        self._health = ExpertHealth.from_dict(payload)
        if self._health.status != "ready":
            raise ExpertNotReadyError(
                f"Remote expert {self.tool_spec.name!r} is {self._health.status}: "
                f"{self._health.message}"
            )
        return self._health

    def health_check(self) -> ExpertHealth:
        return self._health

    def predict(self, invocation_id: str, arguments: Mapping[str, Any]) -> ExpertResult:
        if self._health.status != "ready":
            raise ExpertNotReadyError(
                f"Remote expert {self.tool_spec.name!r} must be prepared before prediction"
            )
        payload = self._request(
            "POST",
            f"{self._tool_path}/invoke",
            {"invocation_id": invocation_id, "arguments": dict(arguments)},
        )
        return ExpertResult.from_dict(payload)

    def shutdown(self) -> None:
        self._health = ExpertHealth(
            tool=self.tool_spec.name,
            backend=self.backend,
            status="not_ready",
            initialized=False,
            message="Remote client shut down.",
            details={"base_url": self.base_url},
        )
