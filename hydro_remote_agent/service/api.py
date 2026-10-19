from pathlib import Path
import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence
from urllib.parse import urlencode

from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import ToolRegistry

from .contracts import JOB_STATUSES, JobSubmission
from .store import JobStore
from .websocket_hub import WorkerHub
from .assets import ArtifactCatalog, ArtifactRecord, MinioAssetStore
from .asset_preview import AssetPreviewService
from .infra import NullEventBus, event_payload
from .workorders import WORKORDER_STATUSES, WorkorderStore
from .task_history import TaskHistoryStore
from .spatial import pixel_to_geographic, pixel_to_projected, projected_to_geographic
from .conversations import AgentChatQueue, JobConversationStore, infer_message_intent
from .workflow_patches import WorkflowPatchStore, infer_workflow_patch


def _validate_asset_roots(assets: Dict[str, str], roots: Sequence[Path]) -> None:
    if not roots:
        return
    resolved_roots = [root.resolve() for root in roots]
    for name, value in assets.items():
        if value.startswith("artifact://"):
            continue
        path = Path(value).resolve()
        if not any(path == root or root in path.parents for root in resolved_roots):
            raise ValueError(f"Asset {name!r} is outside configured dataset roots")


def _publish(bus: Any, payload: dict[str, Any]) -> None:
    try:
        bus.publish(payload)
    except Exception:
        return None


def _artifact_references(value: Any) -> set[str]:
    references: set[str] = set()
    if isinstance(value, str) and value.startswith("artifact://"):
        references.add(value.removeprefix("artifact://"))
    elif isinstance(value, dict):
        artifact_id = value.get("artifact_id")
        if isinstance(artifact_id, str) and artifact_id:
            references.add(artifact_id)
        for item in value.values():
            references.update(_artifact_references(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            references.update(_artifact_references(item))
    return references


def _audit_digest(value: Dict[str, Any]) -> str:
    def normalize(item: Any) -> Any:
        if isinstance(item, bool) or item is None or isinstance(item, str):
            return item
        if isinstance(item, int):
            return str(item)
        if isinstance(item, float):
            if item.is_integer():
                return str(int(item))
            return f"{item:.15f}".rstrip("0").rstrip(".")
        if isinstance(item, dict):
            return {key: normalize(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(child) for child in item]
        return str(item)

    canonical = json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_app(
    store: JobStore,
    registry: ToolRegistry,
    allowed_asset_roots: Sequence[str | Path] = (),
    worker_hub: Optional[WorkerHub] = None,
    asset_store: Optional[MinioAssetStore] = None,
    artifact_catalog: Optional[ArtifactCatalog] = None,
    event_bus: Any = None,
    presence: Any = None,
):
    try:
        from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:
        raise RuntimeError("Agent API requires fastapi") from exc

    roots = tuple(Path(root) for root in allowed_asset_roots)
    bus = event_bus or NullEventBus()
    hub = worker_hub or WorkerHub(presence=presence, store=store)
    catalog = artifact_catalog
    workorders = WorkorderStore(store)
    tasks = TaskHistoryStore(store)
    conversations = JobConversationStore(store)
    chat_queue = AgentChatQueue(store)
    workflow_patches = WorkflowPatchStore(store)
    preview_service = AssetPreviewService(
        asset_store,
        Path(os.getenv("AGENT_STATE_DIR", "runs/agent_state")) / "asset_previews",
    ) if asset_store is not None else None
    map_tile_cache = Path(os.getenv("AGENT_STATE_DIR", "runs/agent_state")) / "map_tiles_osm"
    map_tile_cache.mkdir(parents=True, exist_ok=True)
    map_snapshot_cache = Path(os.getenv("AGENT_STATE_DIR", "runs/agent_state")) / "map_snapshots"
    map_snapshot_cache.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="VagueHydro Agent Service", version="1.0")
    configured_origins = [
        item.strip()
        for item in os.getenv(
            "AGENT_CORS_ORIGINS",
            "http://localhost:4321,http://127.0.0.1:4321,https://localhost,capacitor://localhost",
        ).split(",")
        if item.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["ETag", "Last-Modified"],
    )

    def _workorder_action(action: Any, workorder_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return action(workorder_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workorder not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def _require_worker_secret(value: Optional[str]) -> None:
        expected = getattr(hub, "worker_secret", "")
        if expected and (not value or not hmac.compare_digest(value, expected)):
            raise HTTPException(status_code=401, detail="Invalid worker credential")

    def _publish_latest(job_id: str) -> None:
        _publish(bus, event_payload(job_id, store.events(job_id)[-1]))

    def _record_conversation_event(job_id: str, message: Dict[str, Any]) -> None:
        store.record_event(job_id, "conversation_message", {
            "message_id": message["message_id"], "role": message["role"], "intent": message["intent"],
        })
        _publish_latest(job_id)

    def _chat_context(request: Dict[str, Any]) -> Dict[str, Any]:
        job = store.require(request["job_id"])
        steps = [step.to_dict() for step in list(getattr(store, "steps", lambda _: [])(job.job_id))]
        events = store.events(job.job_id)[-20:]
        messages = conversations.list(job.job_id, limit=100)[-12:]
        job_payload = job.to_dict()
        return {
            "request": request,
            "job": {
                key: job_payload.get(key)
                for key in ("job_id", "request_id", "status", "submission", "plan", "result", "error", "created_at", "updated_at", "version")
            },
            "steps": steps,
            "events": events,
            "messages": messages,
        }

    async def _stop_job_for_intervention(job_id: str) -> Dict[str, Any]:
        current = store.require(job_id)
        if current.status in {"succeeded", "blocked_expert", "failed", "cancelled"}:
            return current.to_dict()
        if current.status in {"planning", "executing"}:
            for step in getattr(store, "steps", lambda _: [])(job_id):
                if step.status in {"dispatched", "running"}:
                    await hub.cancel_task(step.step_id)
                    store.upsert_step(
                        step.step_id, job_id, step.tool, status="cancelled", attempt=step.attempt,
                        worker_id=step.worker_id, progress=step.progress, phase=step.phase,
                        arguments=step.arguments, error={"code": "intervention_cancelled"},
                    )
            stopped = store.transition(
                job_id, current.status, "cancelled",
                error={"code": "user_intervention", "recoverable": True},
                event_type="intervention_cancelled",
            )
        else:
            stopped = store.cancel(job_id)
        _publish_latest(job_id)
        return stopped.to_dict()

    def _planner_asset_token(artifact_id: str, expires: int) -> str:
        secret = getattr(hub, "worker_secret", "")
        return hmac.new(secret.encode("utf-8"), f"{artifact_id}:{expires}".encode("utf-8"), hashlib.sha256).hexdigest()

    @app.get("/healthz")
    def health() -> Dict[str, Any]:
        jobs = store.list_jobs(limit=1000)
        counts: Dict[str, int] = {}
        for job in jobs:
            counts[job.status] = counts.get(job.status, 0) + 1
        return {"status": "ok", "queue": counts}

    @app.get("/v1/map/tiles/{z}/{y}/{x}")
    def map_tile(z: int, y: int, x: int):
        """Proxy and cache public street-map tiles so mobile clients use one backend origin."""
        from fastapi.responses import FileResponse

        if z < 0 or z > 20 or x < 0 or y < 0 or x >= 2 ** z or y >= 2 ** z:
            raise HTTPException(status_code=422, detail="Invalid map tile coordinates")
        tile_path = map_tile_cache / str(z) / str(y) / f"{x}.png"
        if tile_path.is_file() and time.time() - tile_path.stat().st_mtime < 7 * 24 * 3600:
            return FileResponse(tile_path, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})
        tile_path.parent.mkdir(parents=True, exist_ok=True)
        upstream = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        try:
            request = urllib.request.Request(
                upstream,
                headers={"User-Agent": "HydroGuardian/1.0 (water inspection map cache)"},
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                payload = response.read()
                media_type = response.headers.get_content_type()
            if not payload or media_type != "image/png" or not payload.startswith(b"\x89PNG\r\n\x1a\n"):
                raise urllib.error.URLError("empty map tile")
            tile_path.write_bytes(payload)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HTTPException(status_code=502, detail="Map tile upstream unavailable") from exc
        return FileResponse(tile_path, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})

    @app.get("/v1/map/snapshots/guigang-task-area")
    def map_snapshot():
        """Return the pre-cached real map covering the mobile inspection area."""
        from fastapi.responses import FileResponse

        snapshot_path = map_snapshot_cache / "guigang-task-area.jpg"
        if not snapshot_path.is_file():
            raise HTTPException(status_code=404, detail="Map snapshot is not cached")
        return FileResponse(
            snapshot_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=2592000"},
        )

    @app.get("/v1/workers")
    async def workers() -> Dict[str, Any]:
        workers = await hub.snapshot()
        if presence is not None:
            live = {item.get("worker_id"): item for item in presence.snapshot()}
            for worker in workers:
                worker["presence"] = live.get(worker["worker_id"])
        return {"workers": workers}

    @app.post("/v1/assets/presign")
    def presign_asset(payload: Dict[str, Any]) -> Dict[str, Any]:
        if asset_store is None or catalog is None:
            raise HTTPException(status_code=503, detail="Asset storage is not configured")
        filename = payload.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            raise HTTPException(status_code=422, detail="filename is required")
        result = asset_store.presign_upload(
            filename, tenant_id=str(payload.get("tenant_id", "default")),
            job_id=str(payload.get("job_id", "uploads")), media_type=payload.get("media_type"),
        )
        catalog.put(ArtifactRecord(**result["artifact"]))
        result["artifact_uri"] = f"artifact://{result['artifact']['artifact_id']}"
        return result

    @app.post("/v1/assets/{artifact_id}/complete")
    def complete_asset(
        artifact_id: str,
        payload: Dict[str, Any],
        background_tasks: BackgroundTasks,
    ) -> Dict[str, Any]:
        if asset_store is None or catalog is None:
            raise HTTPException(status_code=503, detail="Asset storage is not configured")
        record = catalog.get(artifact_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        updated = asset_store.stat(ArtifactRecord(
            artifact_id=record.artifact_id, bucket=record.bucket, object_key=record.object_key,
            media_type=record.media_type, size_bytes=record.size_bytes,
            sha256=payload.get("sha256") or record.sha256, metadata=dict(payload.get("metadata", {})),
        ))
        catalog.put(updated)
        should_prepare_preview = updated.media_type.startswith("image/") and (
            "tiff" in updated.media_type.lower()
            or (updated.size_bytes or 0) > 8 * 1024 * 1024
        )
        if should_prepare_preview and preview_service is not None:
            background_tasks.add_task(preview_service.render, updated, 2048)
        return updated.to_dict()

    @app.get("/v1/assets/{artifact_id}")
    def get_asset(artifact_id: str) -> Dict[str, Any]:
        if catalog is None:
            raise HTTPException(status_code=503, detail="Asset catalog is not configured")
        record = catalog.get(artifact_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return record.to_dict()

    @app.get("/v1/assets/{artifact_id}/spatial")
    def get_asset_spatial(artifact_id: str) -> Dict[str, Any]:
        if catalog is None:
            raise HTTPException(status_code=503, detail="Asset catalog is not configured")
        record = catalog.get(artifact_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        metadata = dict(record.metadata or {})
        spatial = metadata.get("spatial") or metadata.get("spatial_context")
        if not isinstance(spatial, dict):
            raise HTTPException(status_code=404, detail="Spatial metadata is not available")
        return {"artifact_id": artifact_id, "spatial": spatial}

    @app.post("/v1/spatial/transform")
    def transform_spatial_position(payload: Dict[str, Any]) -> Dict[str, Any]:
        spatial = payload.get("spatial")
        pixel = payload.get("pixel")
        projected = payload.get("projected")
        if isinstance(pixel, dict) and isinstance(spatial, dict):
            try:
                projected_value = pixel_to_projected(spatial, float(pixel["x"]), float(pixel["y"]))
                geographic_value = pixel_to_geographic(spatial, float(pixel["x"]), float(pixel["y"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail="pixel requires numeric x and y") from exc
        elif isinstance(projected, dict):
            try:
                projected_value = (float(projected["x"]), float(projected["y"]))
                epsg = int(payload["source_epsg"])
                geographic_value = projected_to_geographic(projected_value[0], projected_value[1], epsg)
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail="projected coordinates and source_epsg are required") from exc
        else:
            raise HTTPException(status_code=422, detail="Provide pixel with spatial metadata or projected coordinates")
        if projected_value is None or geographic_value is None:
            raise HTTPException(status_code=422, detail="The supplied coordinate reference system is not supported")
        return {
            "projected": {"x": projected_value[0], "y": projected_value[1]},
            "geographic": {"longitude": geographic_value[0], "latitude": geographic_value[1], "crs": "EPSG:4490"},
        }

    @app.get("/v1/assets/{artifact_id}/download")
    def download_asset(artifact_id: str) -> Dict[str, Any]:
        if asset_store is None or catalog is None:
            raise HTTPException(status_code=503, detail="Asset storage is not configured")
        record = catalog.get(artifact_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return {"artifact_id": artifact_id, "download_url": asset_store.presign_download(record)}

    @app.get("/v1/assets/{artifact_id}/preview")
    def preview_asset(artifact_id: str, max_dimension: int = Query(default=2048, ge=512, le=4096)):
        if preview_service is None or catalog is None:
            raise HTTPException(status_code=503, detail="Asset preview is not configured")
        record = catalog.get(artifact_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        try:
            preview = preview_service.render(record, max_dimension=max_dimension)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Artifact preview is unavailable: {exc}") from exc
        from fastapi.responses import FileResponse

        return FileResponse(
            preview,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400, immutable"},
        )

    @app.post("/internal/planner/assets/{artifact_id}/access")
    def access_planner_asset(
        artifact_id: str,
        x_worker_secret: Optional[str] = Header(default=None, alias="X-Worker-Secret"),
    ) -> Dict[str, Any]:
        _require_worker_secret(x_worker_secret)
        if asset_store is None or catalog is None:
            raise HTTPException(status_code=503, detail="Asset storage is not configured")
        if catalog.get(artifact_id) is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        expires = int(time.time()) + 300
        query = urlencode({"expires": expires, "token": _planner_asset_token(artifact_id, expires)})
        return {"artifact_id": artifact_id, "download_path": f"/internal/planner/assets/{artifact_id}?{query}"}

    @app.get("/internal/planner/assets/{artifact_id}")
    def stream_planner_asset(artifact_id: str, expires: int = Query(...), token: str = Query(...)):
        if asset_store is None or catalog is None:
            raise HTTPException(status_code=503, detail="Asset storage is not configured")
        now = int(time.time())
        expected = _planner_asset_token(artifact_id, expires)
        if expires < now or expires > now + 600 or not hmac.compare_digest(token, expected):
            raise HTTPException(status_code=401, detail="Invalid or expired asset access")
        record = catalog.get(artifact_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        from fastapi.responses import StreamingResponse

        response = asset_store.client.get_object(record.bucket, record.object_key)

        def generate():
            try:
                yield from response.stream(1024 * 1024)
            finally:
                response.close()
                response.release_conn()

        headers = {"Content-Length": str(record.size_bytes)} if record.size_bytes is not None else {}
        return StreamingResponse(generate(), media_type=record.media_type, headers=headers)

    @app.post("/internal/tools/{tool_name}/prepare")
    async def prepare_remote_tool(tool_name: str) -> Dict[str, Any]:
        try:
            registry.get(tool_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        workers = await hub.snapshot()
        available = any(tool_name in worker["capabilities"] for worker in workers)
        if not available:
            raise HTTPException(status_code=503, detail=f"No online worker supports {tool_name}")
        return {
            "tool": tool_name,
            "backend": "websocket_expert_worker",
            "status": "ready",
            "initialized": True,
            "message": "Remote WebSocket worker is online.",
            "details": {},
        }

    @app.post("/internal/planner/claim")
    def claim_planning_job(
        x_worker_secret: Optional[str] = Header(default=None, alias="X-Worker-Secret"),
        x_worker_id: Optional[str] = Header(default="remote-planner", alias="X-Worker-Id"),
    ) -> Dict[str, Any]:
        _require_worker_secret(x_worker_secret)
        job = store.claim("planning", x_worker_id or "remote-planner", lease_seconds=1800.0)
        return {"job": job.to_dict() if job else None}

    @app.post("/internal/planner/chat/claim")
    def claim_agent_chat(
        x_worker_secret: Optional[str] = Header(default=None, alias="X-Worker-Secret"),
        x_worker_id: Optional[str] = Header(default="remote-planner", alias="X-Worker-Id"),
    ) -> Dict[str, Any]:
        _require_worker_secret(x_worker_secret)
        request = chat_queue.claim(x_worker_id or "remote-planner", lease_seconds=900.0)
        return {"request": _chat_context(request) if request else None}

    @app.post("/internal/planner/chat/{request_id}/complete")
    def complete_agent_chat(
        request_id: str, payload: Dict[str, Any],
        x_worker_secret: Optional[str] = Header(default=None, alias="X-Worker-Secret"),
    ) -> Dict[str, Any]:
        _require_worker_secret(x_worker_secret)
        answer = str(payload.get("answer") or "").strip()
        if not answer:
            raise HTTPException(status_code=422, detail="answer is required")
        if len(answer) > 4000:
            raise HTTPException(status_code=422, detail="answer must not exceed 4000 characters")
        try:
            request = chat_queue.require(request_id)
            existing_id = f"msg_agent_{request_id}"
            if request["status"] == "succeeded":
                return {"request": request, "message": conversations.require(existing_id)}
            if request["status"] != "running":
                raise RuntimeError(f"Agent conversation request is {request['status']!r}, not running")
            job = store.require(request["job_id"])
            metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
            metadata.update({
                "generated_by": "qwen3_vl_planner",
                "reply_to": request["message_id"],
                "chat_request_id": request_id,
                "job_version": job.version,
            })
            message = conversations.add(
                job.job_id, "assistant", "status", answer, metadata=metadata, message_id=existing_id,
            )
            completed = chat_queue.complete(request_id)
            _record_conversation_event(job.job_id, message)
            return {"request": completed, "message": message}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Agent conversation request not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/internal/planner/chat/{request_id}/fail")
    def fail_agent_chat(
        request_id: str, payload: Dict[str, Any],
        x_worker_secret: Optional[str] = Header(default=None, alias="X-Worker-Secret"),
    ) -> Dict[str, Any]:
        _require_worker_secret(x_worker_secret)
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {
            "code": "agent_chat_failed", "message": str(payload.get("message") or "Agent reply generation failed"),
        }
        try:
            request = chat_queue.require(request_id)
            if request["status"] == "failed":
                return {"request": request}
            failed = chat_queue.fail(request_id, error)
            message = conversations.add(
                request["job_id"], "system", "status", "Agent 本次回复生成未完成，请稍后重新发送。",
                metadata={"reply_to": request["message_id"], "chat_request_id": request_id, "error": error},
                message_id=f"msg_agent_error_{request_id}",
            )
            _record_conversation_event(request["job_id"], message)
            return {"request": failed, "message": message}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Agent conversation request not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/internal/planner/{job_id}/complete")
    def complete_planning_job(
        job_id: str,
        payload: Dict[str, Any],
        x_worker_secret: Optional[str] = Header(default=None, alias="X-Worker-Secret"),
    ) -> Dict[str, Any]:
        _require_worker_secret(x_worker_secret)
        plan = payload.get("plan")
        if not isinstance(plan, dict):
            raise HTTPException(status_code=422, detail="plan is required")
        try:
            request = AgentRequest.from_dict(plan, registry)
            job = store.require(job_id)
            if request.request_id != job.request_id:
                raise ValueError("Planner output request_id does not match the job")
            updated = store.transition(job_id, "planning", "queued_execution", plan=plan, event_type="planning_succeeded")
            _publish(bus, event_payload(job_id, store.events(job_id)[-1]))
            return updated.to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/internal/planner/{job_id}/fail")
    def fail_planning_job(
        job_id: str,
        payload: Dict[str, Any],
        x_worker_secret: Optional[str] = Header(default=None, alias="X-Worker-Secret"),
    ) -> Dict[str, Any]:
        _require_worker_secret(x_worker_secret)
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {"code": "planning_failed", "message": str(payload.get("message") or "Planner failed")}
        try:
            updated = store.transition(job_id, "planning", "failed", error=error, event_type="planning_failed")
            _publish(bus, event_payload(job_id, store.events(job_id)[-1]))
            return updated.to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/internal/tools/{tool_name}/invoke")
    async def invoke_remote_tool(tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        arguments = payload.get("arguments")
        task_id = payload.get("invocation_id")
        if not isinstance(arguments, dict) or not isinstance(task_id, str):
            raise HTTPException(status_code=422, detail="arguments and invocation_id are required")
        try:
            registry.get(tool_name).validate_arguments(arguments)
            return await hub.invoke(
                tool_name,
                arguments,
                task_id=task_id,
                job_id=str(payload.get("job_id", "")),
                timeout=float(payload.get("timeout_seconds", 3600.0)),
            )
        except LookupError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.websocket("/internal/workers/ws")
    async def worker_socket(websocket: WebSocket) -> None:
        session = None
        try:
            await websocket.accept()
            first = await websocket.receive_json()
            from .websocket_protocol import parse_message
            message = parse_message(first)
            if message["type"] != "register":
                raise ValueError("First WebSocket message must be register")
            session = await hub.register(websocket, message)
            while True:
                await hub.receive(session, await websocket.receive_json())
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            try:
                await websocket.close(code=4003, reason=str(exc)[:120])
            except Exception:
                pass
        finally:
            if session is not None:
                await hub.unregister(session.worker_id, websocket)

    @app.post("/v1/jobs", status_code=202)
    def create_job(
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> Dict[str, Any]:
        try:
            submission = JobSubmission.from_dict(payload)
            _validate_asset_roots(submission.assets, roots)
            if submission.planned_request is not None:
                request = AgentRequest.from_dict(submission.planned_request, registry)
                if request.request_id != submission.request_id:
                    raise ValueError("planned_request request_id must match request_id")
            job = store.create_job(submission, idempotency_key)
            task_payload = payload.get("task")
            if task_payload is not None:
                if not isinstance(task_payload, dict):
                    raise ValueError("task must be an object when supplied")
                tasks.upsert(job.job_id, task_payload)
            _publish(bus, event_payload(job.job_id, store.events(job.job_id)[-1]))
            return job.to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/jobs")
    def list_jobs(
        limit: int = Query(default=100, ge=1, le=1000),
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        if status is not None and status not in JOB_STATUSES:
            raise HTTPException(status_code=422, detail="Unsupported job status")
        jobs = store.list_jobs(limit=limit, status=status)
        return {"jobs": [job.to_dict() for job in jobs], "count": len(jobs)}

    @app.get("/v1/jobs/{job_id}")
    def get_job(job_id: str) -> Dict[str, Any]:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job.to_dict()

    @app.get("/v1/jobs/{job_id}/events")
    def get_events(job_id: str) -> Dict[str, Any]:
        if store.get(job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found")
        events = store.events(job_id)
        return {"events": events, "count": len(events)}

    @app.get("/v1/jobs/{job_id}/messages")
    def get_job_messages(job_id: str, limit: int = Query(default=500, ge=1, le=1000)) -> Dict[str, Any]:
        try:
            messages = conversations.list(job_id, limit=limit)
            pending_requests = chat_queue.pending(job_id)
            return {
                "job_id": job_id, "messages": messages, "count": len(messages),
                "pending": bool(pending_requests), "pending_requests": pending_requests,
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.post("/v1/jobs/{job_id}/messages", status_code=201)
    def create_job_message(
        job_id: str, payload: Dict[str, Any],
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> Dict[str, Any]:
        try:
            job = store.require(job_id)
            content = str(payload.get("content") or "").strip()
            requested_intent = str(payload.get("intent") or "auto").strip()
            if requested_intent not in {"auto", "ask", "append_context"}:
                raise ValueError("Message intent must be auto, ask or append_context")
            patch_request = infer_workflow_patch(content, job.submission)
            intent, classification = ("workflow_patch", {
                "classified_by": "workflow_patch_router_v1",
                "matched_signals": [patch_request["tool"]],
                "confidence": "high",
            }) if patch_request else infer_message_intent(content) if requested_intent == "auto" else (
                requested_intent, {"classified_by": "explicit_client", "matched_signals": [], "confidence": "high"},
            )
            user_message = conversations.add(
                job_id, "user", intent, content, metadata={"job_version": job.version, "intent_classification": classification},
                message_id=idempotency_key or payload.get("message_id"),
            )
            _record_conversation_event(job_id, user_message)
            if patch_request is not None:
                registry.get(patch_request["tool"]).validate_arguments(patch_request["arguments"])
                patch = workflow_patches.enqueue(
                    job_id, user_message["message_id"], patch_request["tool"],
                    patch_request["arguments"], patch_request["verification"],
                )
                store.record_event(job_id, "workflow_patch_queued", {
                    "patch_id": patch["patch_id"], "step_id": patch["step_id"],
                    "tool": patch["tool"], "source_message_id": user_message["message_id"],
                    "workflow_version": store.require(job_id).version,
                })
                _publish_latest(job_id)
                tool_labels = {
                    "point_semantic_segmentation": "点云语义分割",
                    "image_change_detection": "前后时相变化检测",
                    "language_guided_point_segmentation": "语言引导点云定位",
                }
                assistant_message = conversations.add(
                    job_id, "assistant", "status",
                    f"已在当前任务中追加“{tool_labels.get(patch['tool'], patch['tool'])}”专家步骤。"
                    "当前执行不会中断；已有结果和证据继续保留，新增步骤将在当前批次结束后接续执行。",
                    metadata={
                        "generated_by": "workflow_orchestrator",
                        "reply_to": user_message["message_id"], "patch_id": patch["patch_id"],
                        "step_id": patch["step_id"], "tool": patch["tool"],
                        "workflow_version": store.require(job_id).version,
                    },
                )
                _record_conversation_event(job_id, assistant_message)
                return {
                    "job_id": job_id, "messages": [user_message, assistant_message],
                    "job": store.require(job_id).to_dict(), "pending": False,
                    "chat_request_id": None, "workflow_patch": patch,
                }
            chat_request = chat_queue.enqueue(job_id, user_message["message_id"])
            return {
                "job_id": job_id,
                "messages": [user_message],
                "job": store.require(job_id).to_dict(),
                "pending": chat_request["status"] in {"queued", "running"},
                "chat_request_id": chat_request["request_id"],
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/v1/jobs/{job_id}/interventions", status_code=202)
    async def intervene_job(
        job_id: str, payload: Dict[str, Any],
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> Dict[str, Any]:
        action = str(payload.get("action") or "").strip()
        if action not in {"cancel", "replan"}:
            raise HTTPException(status_code=422, detail="action must be cancel or replan")
        if payload.get("confirmed") is not True:
            raise HTTPException(status_code=409, detail={"message": "This intervention requires confirmation", "confirmation_required": True})
        try:
            current = store.require(job_id)
            instruction = str(payload.get("content") or "").strip()
            if action == "replan" and not instruction:
                raise ValueError("content is required for replan")
            user_message = conversations.add(
                job_id, "user", action, instruction or "停止当前任务", metadata={"job_version": current.version},
                message_id=idempotency_key or payload.get("message_id"),
            )
            _record_conversation_event(job_id, user_message)
            await _stop_job_for_intervention(job_id)
            if action == "cancel":
                reply = conversations.add(job_id, "assistant", "status", "任务已安全停止，已有执行记录和结果产物继续保留。", metadata={"reply_to": user_message["message_id"]})
                _record_conversation_event(job_id, reply)
                return {"action": action, "job": store.require(job_id).to_dict(), "messages": [user_message, reply]}

            contexts = conversations.context(job_id)
            original_query = str(current.submission.get("query") or "").strip()
            query_parts = [original_query]
            if contexts:
                query_parts.append("补充上下文：" + "；".join(contexts))
            query_parts.append("本次调整：" + instruction)
            request_id = f"{current.request_id}-replan-{uuid.uuid4().hex[:12]}"
            submission = JobSubmission(
                request_id=request_id, query="\n".join(query_parts),
                assets=dict(current.submission.get("assets") or {}),
                language=str(current.submission.get("language") or "auto"),
            )
            next_job = store.create_job(submission, idempotency_key and f"replan:{idempotency_key}")
            previous_task = next((item for item in tasks.list(limit=1000) if item.get("job_id") == job_id), None)
            if previous_task is not None:
                tasks.rebind_job(previous_task["task_id"], next_job.job_id, {"parent_job_id": job_id, "replan_instruction": instruction})
            system_message = conversations.add(
                next_job.job_id, "system", "status", "已根据人工调整创建新的规划任务。",
                metadata={"parent_job_id": job_id, "source_message_id": user_message["message_id"]},
            )
            store.record_event(next_job.job_id, "intervention_replanned", {"parent_job_id": job_id, "message_id": user_message["message_id"]})
            _publish_latest(next_job.job_id)
            reply = conversations.add(
                job_id, "assistant", "status", "当前执行已停止，新的任务规划已经创建。",
                metadata={"reply_to": user_message["message_id"], "next_job_id": next_job.job_id},
            )
            _record_conversation_event(job_id, reply)
            return {
                "action": action, "previous_job": store.require(job_id).to_dict(), "job": next_job.to_dict(),
                "task": tasks.require(previous_task["task_id"]) if previous_task is not None else None,
                "messages": [user_message, reply, system_message],
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/jobs/{job_id}/events/stream")
    async def stream_events(job_id: str, last_event_id: int = Query(default=0, ge=0)):
        from fastapi.responses import StreamingResponse

        if store.get(job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found")

        async def generate():
            cursor = last_event_id
            while True:
                events = [event for event in store.events(job_id) if event["event_id"] > cursor]
                for event in events:
                    cursor = event["event_id"]
                    yield f"id: {cursor}\nevent: job\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                job = store.get(job_id)
                if job is None or (job.status in {"succeeded", "blocked_expert", "failed", "cancelled"} and not events):
                    break
                if not events:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(1.0)

        return StreamingResponse(generate(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no",
        })

    @app.get("/v1/jobs/{job_id}/artifacts")
    def get_artifacts(job_id: str) -> Dict[str, Any]:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        result = job.result or {}
        artifacts = result.get("terminal_artifacts", {})
        return {
            "job_id": job_id,
            "artifacts": artifacts if isinstance(artifacts, dict) else {},
        }

    @app.get("/v1/jobs/{job_id}/steps")
    def get_steps(job_id: str) -> Dict[str, Any]:
        if store.get(job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found")
        steps = getattr(store, "steps", lambda _: [])(job_id)
        return {"job_id": job_id, "steps": [step.to_dict() for step in steps], "count": len(steps)}

    @app.get("/v1/reports/jobs/{job_id}")
    def get_job_audit_report(job_id: str) -> Dict[str, Any]:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        job_payload = job.to_dict()
        steps_payload = [step.to_dict() for step in store.steps(job_id)]
        events_payload = store.events(job_id)
        workorder_payload = workorders.list(job_id=job_id, limit=1000)
        task_payload = next((item for item in tasks.list(limit=1000) if item.get("job_id") == job_id), None)
        artifact_ids = _artifact_references({
            "job": job_payload,
            "steps": steps_payload,
            "workorders": workorder_payload,
        })
        artifacts_payload = []
        for artifact_id in sorted(artifact_ids):
            record = catalog.get(artifact_id) if catalog is not None else None
            artifacts_payload.append(record.to_dict() if record is not None else {
                "artifact_id": artifact_id,
                "catalog_status": "unavailable",
            })
        result = job.result or {}
        report: Dict[str, Any] = {
            "schema_version": "hydro-audit-report.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "subject": {
                "job_id": job_id,
                "task_id": task_payload.get("task_id") if task_payload else None,
                "request_id": job.request_id,
                "trace_id": job.trace_id,
                "status": job.status,
            },
            "task": task_payload,
            "job": job_payload,
            "execution": {
                "plan": job.plan,
                "steps": steps_payload,
                "events": events_payload,
                "messages": conversations.list(job_id),
            },
            "findings": {
                "risk_candidates": result.get("risk_candidates", []),
                "quality": result.get("quality") or result.get("quality_report"),
                "spatial_context": result.get("spatial_context"),
                "terminal_artifacts": result.get("terminal_artifacts", {}),
            },
            "artifacts": artifacts_payload,
            "workorders": workorder_payload,
        }
        report["integrity"] = {
            "algorithm": "SHA-256",
            "digest": _audit_digest(report),
            "scope": "报告中除 integrity 字段外的规范化 JSON 内容",
            "artifact_count": len(artifacts_payload),
            "event_count": len(events_payload),
        }
        return report

    @app.get("/v1/tasks")
    def list_tasks(
        limit: int = Query(default=100, ge=1, le=1000),
        status: Optional[str] = None,
        zone_id: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        if status is not None and status not in JOB_STATUSES:
            raise HTTPException(status_code=422, detail="Unsupported job status")
        items = tasks.list(limit=limit, status=status, zone_id=zone_id, keyword=keyword)
        return {"tasks": items, "count": len(items)}

    @app.post("/v1/tasks", status_code=201)
    def register_task(payload: Dict[str, Any]) -> Dict[str, Any]:
        job_id = payload.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            raise HTTPException(status_code=422, detail="job_id is required")
        try:
            return tasks.upsert(job_id.strip(), payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Agent job not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/tasks/{task_id}")
    def get_task(task_id: str) -> Dict[str, Any]:
        try:
            return tasks.require(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    @app.get("/v1/tasks/{task_id}/history")
    def get_task_history(task_id: str) -> Dict[str, Any]:
        try:
            history = tasks.history(task_id)
            history["workorders"] = workorders.list(job_id=history["task"]["job_id"], limit=1000)
            return history
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    @app.post("/v1/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> Dict[str, Any]:
        current = store.get(job_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if current.status in {"planning", "executing"}:
            cancelled = False
            for step in getattr(store, "steps", lambda _: [])(job_id):
                if step.status in {"dispatched", "running"}:
                    cancelled = await hub.cancel_task(step.step_id) or cancelled
                    store.upsert_step(step.step_id, job_id, step.tool, status="cancelled", attempt=step.attempt,
                                      worker_id=step.worker_id, progress=step.progress, phase=step.phase,
                                      arguments=step.arguments, error={"code": "cancelled"})
            raise HTTPException(status_code=409, detail={"message": "Job is running", "cancel_sent": cancelled})
        try:
            job = store.cancel(job_id)
            _publish(bus, event_payload(job.job_id, store.events(job.job_id)[-1]))
            return job.to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str) -> Dict[str, Any]:
        try:
            job = store.retry(job_id)
            _publish(bus, event_payload(job.job_id, store.events(job.job_id)[-1]))
            return job.to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/workorders", status_code=201)
    def create_workorder(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return workorders.create_from_candidate(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Agent job not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/workorders")
    def list_workorders(
        limit: int = Query(default=100, ge=1, le=1000),
        status: Optional[str] = None,
        task_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if status is not None and status not in WORKORDER_STATUSES:
            raise HTTPException(status_code=422, detail="Unsupported workorder status")
        items = workorders.list(status=status, task_id=task_id, job_id=job_id, limit=limit)
        return {"workorders": items, "count": len(items)}

    @app.get("/v1/workorders/{workorder_id}")
    def get_workorder(workorder_id: str) -> Dict[str, Any]:
        try:
            return workorders.aggregate(workorder_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workorder not found") from exc

    @app.post("/v1/workorders/{workorder_id}/assign")
    def assign_workorder(workorder_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _workorder_action(workorders.assign, workorder_id, payload)

    @app.post("/v1/workorders/{workorder_id}/start")
    def start_workorder(workorder_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _workorder_action(workorders.start, workorder_id, payload)

    @app.post("/v1/workorders/{workorder_id}/feedback")
    def feedback_workorder(
        workorder_id: str,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> Dict[str, Any]:
        try:
            if idempotency_key and not payload.get("client_submission_id"):
                payload["client_submission_id"] = idempotency_key
            return workorders.feedback(workorder_id, payload, catalog=catalog)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workorder not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/workorders/{workorder_id}/review")
    def review_workorder(workorder_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _workorder_action(workorders.review, workorder_id, payload)

    return app
