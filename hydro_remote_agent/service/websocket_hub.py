from __future__ import annotations

import asyncio
import time
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .websocket_protocol import (
    ProtocolError,
    make_message,
    parse_message,
    verify_worker_auth,
)
from .assets import ArtifactCatalog, resolve_artifact_references
from .infra import RedisPresence


@dataclass
class WorkerSession:
    worker_id: str
    websocket: Any
    capabilities: set[str] = field(default_factory=set)
    gpus: list[dict[str, Any]] = field(default_factory=list)
    version: str = "unknown"
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    pending: Dict[str, dict[str, Any]] = field(default_factory=dict)


class WorkerHub:
    """In-process WebSocket control plane for actively connecting GPU workers."""

    def __init__(self, worker_secret: str = "", auth_max_age: float = 120.0,
                 artifact_catalog: Optional[ArtifactCatalog] = None,
                 presence: Optional[RedisPresence] = None,
                 store: Any = None) -> None:
        self.worker_secret = worker_secret
        self.auth_max_age = auth_max_age
        self._workers: dict[str, WorkerSession] = {}
        self._lock = asyncio.Lock()
        self._results: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._auth_nonces: dict[str, float] = {}
        self.artifact_catalog = artifact_catalog
        self.presence = presence
        self.store = store

    @staticmethod
    def _job_id(task_id: str, supplied: str = "") -> str:
        if supplied:
            return supplied
        match = re.match(r"^(job_[^_]+(?:_[^_]+)*)_a\d+", task_id)
        return match.group(1) if match else ""

    def _step_exists(self, step_id: str) -> bool:
        try:
            self.store.step(step_id)
            return True
        except KeyError:
            return False

    def _step_update(self, message: dict[str, Any], status: str, *, worker_id: str) -> None:
        if self.store is None:
            return
        task_id = message.get("task_id")
        if not isinstance(task_id, str):
            return
        job_id = self._job_id(task_id, str(message.get("job_id", "")))
        if not job_id:
            return
        tool = str(message.get("tool", "unknown"))
        existing_step = self.store.step(task_id) if self._step_exists(task_id) else None
        if tool == "unknown" and existing_step is not None:
            tool = existing_step.tool
        payload = message.get("result") if status == "succeeded" else message.get("error")
        step = self.store.upsert_step(
            task_id, job_id, tool, status=status, attempt=int(message.get("attempt", 1)),
            worker_id=worker_id, progress=float(message.get("progress", 1.0 if status in {"succeeded", "failed"} else 0.0)),
            phase=str(message.get("phase", "")), result=payload if status == "succeeded" and isinstance(payload, dict) else None,
            error=payload if status == "failed" and isinstance(payload, dict) else None,
            arguments=existing_step.arguments if existing_step is not None else None,
        )
        event_type = "step_progress" if status == "running" else f"step_{status}"
        self.store.record_event(job_id, event_type, step.to_dict())

    async def register(self, websocket: Any, message: dict[str, Any]) -> WorkerSession:
        worker_id = message.get("worker_id")
        capabilities = message.get("capabilities", [])
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ProtocolError("register.worker_id must be non-empty")
        if not isinstance(capabilities, list) or not all(isinstance(x, str) for x in capabilities):
            raise ProtocolError("register.capabilities must be a string array")
        if self.worker_secret and not verify_worker_auth(message, self.worker_secret, self.auth_max_age):
            raise ProtocolError("Worker authentication failed")
        nonce = str(message.get("auth_nonce", ""))
        now = time.time()
        async with self._lock:
            self._auth_nonces = {
                key: seen_at for key, seen_at in self._auth_nonces.items()
                if now - seen_at <= self.auth_max_age
            }
            if self.worker_secret and nonce in self._auth_nonces:
                raise ProtocolError("Worker authentication nonce was already used")
            if self.worker_secret:
                self._auth_nonces[nonce] = now
        session = WorkerSession(
            worker_id=worker_id,
            websocket=websocket,
            capabilities=set(capabilities),
            gpus=list(message.get("gpus", [])) if isinstance(message.get("gpus", []), list) else [],
            version=str(message.get("worker_version", "unknown")),
        )
        async with self._lock:
            previous = self._workers.get(worker_id)
            self._workers[worker_id] = session
        if previous is not None and previous.websocket is not websocket:
            await previous.websocket.close(code=4001, reason="Replaced by a newer connection")
        await websocket.send_json(make_message(
            "registered",
            worker_id=worker_id,
            heartbeat_interval_seconds=15,
            lease_seconds=1800,
            capabilities=sorted(session.capabilities),
        ))
        if self.presence is not None:
            self.presence.heartbeat(worker_id, {
                "worker_id": worker_id, "version": session.version,
                "capabilities": sorted(session.capabilities), "last_heartbeat": session.last_heartbeat,
            })
        await self._recover_for_worker(session)
        return session

    async def _recover_for_worker(self, session: WorkerSession) -> None:
        if self.store is None or not hasattr(self.store, "recoverable_steps"):
            return
        for step in self.store.recoverable_steps():
            job = self.store.get(step.job_id)
            if job is None or job.status in {"succeeded", "blocked_expert", "failed", "cancelled"}:
                continue
            if step.tool not in session.capabilities:
                continue
            if step.step_id in session.pending:
                continue
            await self.dispatch(
                step.tool,
                step.arguments,
                task_id=step.step_id,
                job_id=step.job_id,
                attempt=step.attempt + 1,
            )

    async def unregister(self, worker_id: str, websocket: Any) -> None:
        disconnected_tasks: list[str] = []
        async with self._lock:
            current = self._workers.get(worker_id)
            if current is not None and current.websocket is websocket:
                disconnected_tasks = list(current.pending)
                self._workers.pop(worker_id, None)
                if self.presence is not None:
                    self.presence.remove(worker_id)
                if self.store is not None:
                    self.store.mark_lost_steps(worker_id)
            for task_id in disconnected_tasks:
                future = self._results.get(task_id)
                if future is not None and not future.done():
                    future.set_exception(ConnectionError(f"Worker {worker_id!r} disconnected"))

    async def receive(self, session: WorkerSession, raw: Any) -> dict[str, Any]:
        message = parse_message(raw)
        message_type = message["type"]
        message_id = str(message.get("message_id", ""))
        if self.store is not None and message_id and hasattr(self.store, "claim_message"):
            if not self.store.claim_message(message_id, session.worker_id, message_type):
                return message
        task_id = message.get("task_id")
        if isinstance(task_id, str):
            original = session.pending.get(task_id, {})
            for key in ("job_id", "tool"):
                if key not in message and key in original:
                    message[key] = original[key]
        if message_type in {"heartbeat", "progress"}:
            session.last_heartbeat = time.time()
            if self.presence is not None:
                self.presence.heartbeat(session.worker_id, {
                    "worker_id": session.worker_id, "version": session.version,
                    "capabilities": sorted(session.capabilities), "last_heartbeat": session.last_heartbeat,
                })
        if message_type == "progress":
            self._step_update(message, "running", worker_id=session.worker_id)
        if message_type == "task_ack":
            task_id = message.get("task_id")
            if isinstance(task_id, str) and task_id in session.pending:
                session.pending[task_id]["acknowledged"] = True
        if message_type in {"completed", "failed", "cancelled"}:
            if isinstance(task_id, str):
                session.pending.pop(task_id, None)
                terminal_status = {
                    "completed": "succeeded", "failed": "failed", "cancelled": "cancelled",
                }[message_type]
                self._step_update(message, terminal_status, worker_id=session.worker_id)
                if message_type == "completed" and self.artifact_catalog is not None:
                    for payload in message.get("produced_artifacts", []):
                        if isinstance(payload, dict):
                            from .assets import ArtifactRecord

                            self.artifact_catalog.put(ArtifactRecord(**payload))
                future = self._results.get(task_id)
                if future is not None and not future.done():
                    if message_type == "cancelled":
                        future.set_exception(asyncio.CancelledError())
                    else:
                        future.set_result(message)
        return message

    async def dispatch(self, tool: str, arguments: dict[str, Any], *, task_id: str, job_id: str = "", attempt: int = 1) -> str:
        async with self._lock:
            candidates = [worker for worker in self._workers.values() if tool in worker.capabilities]
            if not candidates:
                raise LookupError(f"No online worker supports tool {tool!r}")
            session = min(candidates, key=lambda item: len(item.pending))
            resolved_arguments = (
                resolve_artifact_references(arguments, self.artifact_catalog)
                if self.artifact_catalog is not None else arguments
            )
            message = make_message(
                "task", task_id=task_id, job_id=job_id, tool=tool, arguments=resolved_arguments,
                attempt=attempt,
            )
            session.pending[task_id] = message
            if self.store is not None and job_id:
                self.store.upsert_step(task_id, job_id, tool, status="dispatched", attempt=attempt, worker_id=session.worker_id, arguments=resolved_arguments)
                self.store.record_event(job_id, "step_dispatched", self.store.step(task_id).to_dict())
        await session.websocket.send_json(message)
        return session.worker_id

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            for session in self._workers.values():
                if task_id in session.pending:
                    await session.websocket.send_json(make_message(
                        "cancel", worker_id=session.worker_id, task_id=task_id
                    ))
                    return True
        return False

    async def invoke(
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        task_id: str,
        job_id: str = "",
        timeout: float = 3600.0,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        async with self._lock:
            if task_id in self._results:
                raise ValueError(f"Task {task_id!r} is already active")
            self._results[task_id] = future
        try:
            await self.dispatch(tool, arguments, task_id=task_id, job_id=job_id)
            message = await asyncio.wait_for(future, timeout=max(timeout, 1.0))
            if message["type"] == "failed":
                error = message.get("error", {})
                raise RuntimeError(str(error.get("message", "Remote worker failed")))
            result = message.get("result")
            if not isinstance(result, dict):
                raise RuntimeError("Remote worker returned no result")
            return result
        finally:
            async with self._lock:
                self._results.pop(task_id, None)

    async def snapshot(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                {
                    "worker_id": worker.worker_id,
                    "version": worker.version,
                    "capabilities": sorted(worker.capabilities),
                    "gpus": worker.gpus,
                    "connected_at": worker.connected_at,
                    "last_heartbeat": worker.last_heartbeat,
                    "pending_tasks": sorted(worker.pending),
                }
                for worker in self._workers.values()
            ]
