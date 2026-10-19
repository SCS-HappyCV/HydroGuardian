from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from hydro_remote_agent.evaluation.routing import parse_json_response
from hydro_remote_agent.schemas.agent_action import AgentRequest


TERMINAL_JOB_STATUSES = {"succeeded", "blocked_expert", "failed", "cancelled"}


class AgentServiceExecutionClient:
    """Execute a frozen AgentRequest through the deployed WebSocket-worker service."""

    def __init__(
        self,
        base_url: str,
        work_dir: str | Path,
        timeout_seconds: float = 1800.0,
        poll_seconds: float = 0.5,
        artifact_proxy_url: Optional[str] = None,
        idempotency_namespace: str = "task-aware-240",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.work_dir = Path(work_dir)
        self.timeout_seconds = max(float(timeout_seconds), 1.0)
        self.poll_seconds = max(float(poll_seconds), 0.05)
        self.artifact_proxy_url = (
            artifact_proxy_url.rstrip("/") if artifact_proxy_url else None
        )
        self.idempotency_namespace = idempotency_namespace.strip()
        if not self.idempotency_namespace:
            raise ValueError("idempotency_namespace must be non-empty")
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def _artifact_download_request(self, download_url: str) -> Request:
        if not self.artifact_proxy_url:
            return Request(download_url)
        original = urlparse(download_url)
        proxy = urlparse(self.artifact_proxy_url)
        if not proxy.scheme or not proxy.netloc:
            raise ValueError("artifact_proxy_url must include scheme and host")
        routed = urlunparse(
            (proxy.scheme, proxy.netloc, original.path, original.params, original.query, "")
        )
        return Request(routed, headers={"Host": original.netloc})

    def _json_request(
        self,
        method: str,
        path: str,
        payload: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        body = None
        request_headers = {"Accept": "application/json", **dict(headers or {})}
        if payload is not None:
            body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Agent service HTTP {exc.code} for {path}: {details}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Agent service request failed for {path}: {exc}") from exc
        if not isinstance(result, dict):
            raise RuntimeError(f"Agent service response for {path} must be an object")
        return result

    @staticmethod
    def _submission_context(record: Mapping[str, Any]) -> Tuple[str, Dict[str, str], str]:
        for message in record.get("messages", []):
            if not isinstance(message, Mapping) or message.get("role") != "user":
                continue
            try:
                payload = json.loads(str(message.get("content", "")))
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, Mapping):
                continue
            query = str(payload.get("query", "")).strip()
            raw_assets = payload.get("assets")
            assets = (
                {
                    str(name): str(value)
                    for name, value in raw_assets.items()
                    if isinstance(name, str) and isinstance(value, str)
                }
                if isinstance(raw_assets, Mapping)
                else {}
            )
            language = str(payload.get("language") or record.get("language") or "auto")
            if query:
                return query, assets, language
        raise ValueError(f"Record {record.get('id')!r} has no valid user query payload")

    def _download_artifact(self, artifact_uri: str, job_id: str, name: str) -> Path:
        artifact_id = artifact_uri[len("artifact://") :]
        metadata = self._json_request("GET", f"/v1/assets/{artifact_id}")
        download = self._json_request("GET", f"/v1/assets/{artifact_id}/download")
        object_key = str(metadata.get("object_key", ""))
        filename = Path(object_key).name or f"{name}.bin"
        target = self.work_dir / "artifacts" / job_id / name / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            request = self._artifact_download_request(str(download["download_url"]))
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read()
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Failed to download {artifact_uri}: {exc}") from exc
        expected_sha256 = str(metadata.get("sha256", ""))
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if expected_sha256 and actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"Artifact SHA256 mismatch for {artifact_uri}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        target.write_bytes(content)
        return target

    def _materialize_artifacts(self, result: Dict[str, Any], job_id: str) -> Dict[str, Any]:
        terminal = result.get("terminal_artifacts")
        uri_to_path: Dict[str, str] = {}
        if isinstance(terminal, Mapping):
            for name, value in terminal.items():
                if isinstance(value, str) and value.startswith("artifact://"):
                    uri_to_path[value] = str(self._download_artifact(value, job_id, str(name)))

        def replace(value: Any) -> Any:
            if isinstance(value, str):
                return uri_to_path.get(value, value)
            if isinstance(value, list):
                return [replace(item) for item in value]
            if isinstance(value, Mapping):
                return {str(key): replace(item) for key, item in value.items()}
            return value

        return replace(result)

    def execute_prediction(
        self,
        prediction: str,
        request_id: str,
        phase: str,
        record: Mapping[str, Any],
        registry,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], float]:
        started = time.perf_counter()
        payload: Optional[Dict[str, Any]] = None
        try:
            payload = parse_json_response(prediction)
            request = AgentRequest.from_dict(payload, registry)
            if request.request_id != request_id:
                raise ValueError("Planner changed request_id")
            query, _assets, language = self._submission_context(record)
            idempotency_key = f"{self.idempotency_namespace}:{phase}:{request_id}"
            job = self._json_request(
                "POST",
                "/v1/jobs",
                {
                    "request_id": request_id,
                    "query": query,
                    # The control plane can run on a different host and therefore
                    # cannot validate worker-local dataset paths. Frozen paths stay
                    # unchanged in planned_request, which is what workers execute.
                    "assets": {},
                    "language": language,
                    "planned_request": payload,
                },
                {"Idempotency-Key": idempotency_key},
            )
            job_id = str(job["job_id"])
            deadline = time.monotonic() + self.timeout_seconds
            while str(job.get("status")) not in TERMINAL_JOB_STATUSES:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Agent service job {job_id} exceeded timeout")
                time.sleep(self.poll_seconds)
                job = self._json_request("GET", f"/v1/jobs/{job_id}")
            status = str(job.get("status", "failed"))
            raw_result = job.get("result")
            if status == "succeeded" and isinstance(raw_result, Mapping):
                result = self._materialize_artifacts(dict(raw_result), job_id)
                execution = {
                    "id": request_id,
                    "status": "succeeded",
                    "result": result,
                    "service_job_id": job_id,
                }
                return execution, payload, (time.perf_counter() - started) * 1000.0
            error = job.get("error") or {
                "status": status,
                "message": "Agent service did not produce a successful result",
            }
            return (
                {
                    "id": request_id,
                    "status": "failed",
                    "error": f"AgentServiceJobError: {json.dumps(error, ensure_ascii=False)}",
                    "service_job_id": job_id,
                    "service_status": status,
                },
                payload,
                (time.perf_counter() - started) * 1000.0,
            )
        except Exception as exc:
            return (
                {
                    "id": request_id,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                payload,
                (time.perf_counter() - started) * 1000.0,
            )

    def shutdown(self) -> None:
        return None
