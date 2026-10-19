from __future__ import annotations

import argparse
import asyncio
import functools
import json
import os
import random
import secrets
import time
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.runtime import load_expert_runtime
from hydro_remote_agent.schemas.tool_spec import ToolRegistry, load_tool_registry
from hydro_remote_agent.service.websocket_protocol import make_message, parse_message, sign_worker_payload
from hydro_remote_agent.service.assets import MinioAssetStore
from hydro_remote_agent.service.worker_assets import WorkerAssetManager


DEFAULT_MAX_SOURCE_IMAGE_PIXELS = 350_000_000


def select_capability_registry(
    registry: ToolRegistry,
    capabilities: Sequence[str],
) -> ToolRegistry:
    selected = tuple(capabilities)
    duplicates = sorted({name for name in selected if selected.count(name) > 1})
    if duplicates:
        raise ValueError(f"Duplicate worker capabilities: {duplicates}")
    unknown = sorted(set(selected) - set(registry.names()))
    if unknown:
        raise ValueError(f"Unknown worker capabilities: {unknown}")
    return ToolRegistry(
        schema_version=registry.schema_version,
        tools=tuple(registry.get(name) for name in selected),
    )


def configure_source_image_limit() -> Optional[int]:
    raw_limit = os.getenv(
        "EXPERT_MAX_SOURCE_IMAGE_PIXELS",
        str(DEFAULT_MAX_SOURCE_IMAGE_PIXELS),
    ).strip()
    limit = int(raw_limit)
    if limit <= 0:
        raise ValueError("EXPERT_MAX_SOURCE_IMAGE_PIXELS must be positive")
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = max(Image.MAX_IMAGE_PIXELS or 0, limit)
    return Image.MAX_IMAGE_PIXELS


async def _to_thread(function, /, *args, **kwargs):
    loop = asyncio.get_running_loop()
    call = functools.partial(function, *args, **kwargs)
    return await loop.run_in_executor(None, call)


async def _heartbeat(socket, worker_id: str, interval: float = 15.0) -> None:
    while True:
        await asyncio.sleep(interval)
        await socket.send(json.dumps(make_message(
            "heartbeat", worker_id=worker_id, status="online"
        )))


async def run_worker(args: argparse.Namespace) -> None:
    try:
        import websockets
        from websockets.exceptions import WebSocketException
    except ImportError as exc:
        raise RuntimeError("WebSocket Worker requires websockets") from exc
    configured_image_limit = configure_source_image_limit()
    if configured_image_limit is not None:
        print(f"EXPERT_SOURCE_IMAGE_LIMIT pixels={configured_image_limit}", flush=True)
    full_registry = load_tool_registry(args.registry)
    capabilities = tuple(args.capability or full_registry.names())
    registry = select_capability_registry(full_registry, capabilities)
    runtime = load_expert_runtime(args.runtime, registry, work_dir=args.work_dir)
    asset_manager = None
    if args.minio_endpoint:
        asset_manager = WorkerAssetManager(
            MinioAssetStore(
                args.minio_endpoint, args.minio_access_key, args.minio_secret_key,
                secure=args.minio_secure, input_bucket=args.minio_input_bucket,
                output_bucket=args.minio_output_bucket,
            ),
            Path(args.work_dir) / "assets",
        )
    worker_id = args.worker_id or f"gpu-worker-{secrets.token_hex(4)}"
    prepared: set[str] = set()
    active_tasks: dict[str, asyncio.Task] = {}
    cancel_events: dict[str, asyncio.Event] = {}
    reconnect_delay = 1.0
    try:
        while True:
            try:
                nonce = secrets.token_hex(16)
                timestamp = int(time.time())
                register = make_message(
                    "register",
                    worker_id=worker_id,
                    worker_version=args.worker_version,
                    capabilities=list(capabilities),
                    gpus=[],
                    auth_timestamp=str(timestamp),
                    auth_nonce=nonce,
                    auth_signature=sign_worker_payload(worker_id, timestamp, nonce, args.worker_secret)
                    if args.worker_secret else "",
                )
                async with websockets.connect(
                    args.agent_ws_url,
                    ping_interval=None,
                    ping_timeout=None,
                ) as socket:
                    await socket.send(json.dumps(register))
                    registered = parse_message(await socket.recv())
                    if registered["type"] != "registered":
                        raise RuntimeError(
                            f"Agent did not register the worker: {registered.get('type', 'unknown')}"
                        )
                    reconnect_delay = 1.0
                    heartbeat = asyncio.create_task(_heartbeat(socket, worker_id))
                    async def send_cancelled(task_id: str) -> None:
                        await socket.send(json.dumps(make_message(
                            "cancelled", worker_id=worker_id, task_id=task_id,
                            error={"code": "cancelled", "message": "Cancellation requested."},
                        )))

                    async def process_task(message: dict) -> None:
                        task_id = message.get("task_id")
                        tool = message.get("tool")
                        arguments = message.get("arguments")
                        if not isinstance(task_id, str) or not isinstance(tool, str) or not isinstance(arguments, dict):
                            return
                        cancel_event = asyncio.Event()
                        cancel_events[task_id] = cancel_event
                        try:
                            await socket.send(json.dumps(make_message(
                                "progress", worker_id=worker_id, task_id=task_id, progress=0.0, phase="started"
                            )))
                            local_arguments = (
                                await _to_thread(asset_manager.materialize, arguments, task_id)
                                if asset_manager is not None else arguments
                            )
                            if cancel_event.is_set():
                                await send_cancelled(task_id)
                                return
                            if tool not in prepared:
                                await _to_thread(runtime.prepare, tool)
                                prepared.add(tool)
                            if cancel_event.is_set():
                                await send_cancelled(task_id)
                                return
                            result = await _to_thread(runtime.invoke, tool, local_arguments, task_id)
                            if cancel_event.is_set():
                                await send_cancelled(task_id)
                                return
                            result_payload = result.to_dict()
                            produced_artifacts = []
                            if asset_manager is not None:
                                result_payload, produced_artifacts = await _to_thread(
                                    asset_manager.publish_result, result_payload, task_id,
                                    str(message.get("job_id", "")), arguments,
                                )
                            await socket.send(json.dumps(make_message(
                                "completed", worker_id=worker_id, task_id=task_id,
                                result=result_payload, produced_artifacts=produced_artifacts,
                            )))
                        except Exception as exc:
                            if not cancel_event.is_set():
                                await socket.send(json.dumps(make_message(
                                    "failed", worker_id=worker_id, task_id=task_id, error={
                                        "code": type(exc).__name__, "message": str(exc), "recoverable": False
                                    }
                                )))
                            else:
                                await send_cancelled(task_id)
                        finally:
                            cancel_events.pop(task_id, None)
                            active_tasks.pop(task_id, None)
                            if asset_manager is not None:
                                asset_manager.cleanup(task_id)

                    async for raw in socket:
                        message = parse_message(raw)
                        if message["type"] == "cancel":
                            task_id = message.get("task_id")
                            if isinstance(task_id, str) and task_id in cancel_events:
                                cancel_events[task_id].set()
                                await socket.send(json.dumps(make_message(
                                    "cancel_ack", worker_id=worker_id, task_id=task_id,
                                )))
                            continue
                        if message["type"] != "task":
                            continue
                        task_id = message.get("task_id")
                        if not isinstance(task_id, str) or task_id in active_tasks:
                            continue
                        await socket.send(json.dumps(make_message(
                            "task_ack", worker_id=worker_id, task_id=task_id
                        )))
                        active_tasks[task_id] = asyncio.create_task(process_task(message))
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)
            except (OSError, RuntimeError, WebSocketException) as exc:
                print(
                    f"EXPERT_WORKER_RECONNECT error={type(exc).__name__}: {exc} "
                    f"retry_seconds={reconnect_delay:.1f}",
                    flush=True,
                )
                await asyncio.sleep(reconnect_delay + random.random())
                reconnect_delay = min(reconnect_delay * 2.0, 30.0)
    finally:
        runtime.shutdown()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the active WebSocket Expert Worker client.")
    package_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--agent-ws-url", default=os.getenv("AGENT_WS_URL", "ws://127.0.0.1:18080/internal/workers/ws"))
    parser.add_argument("--registry", default=str(package_root / "configs" / "tool_registry.yaml"))
    parser.add_argument("--runtime", default=str(package_root / "configs" / "expert_runtime.yaml"))
    parser.add_argument("--work-dir", default=os.getenv("EXPERT_WORK_DIR", "/data/expert_outputs"))
    parser.add_argument("--worker-id", default=os.getenv("WORKER_ID"))
    parser.add_argument("--worker-version", default=os.getenv("WORKER_VERSION", "dev"))
    parser.add_argument(
        "--capability", action="append", default=[],
        help="Advertise only this tool capability; repeat for multiple tools.",
    )
    parser.add_argument("--worker-secret", default=os.getenv("WORKER_SECRET", ""))
    parser.add_argument("--minio-endpoint", default=os.getenv("MINIO_ENDPOINT", ""))
    parser.add_argument("--minio-access-key", default=os.getenv("MINIO_ACCESS_KEY", ""))
    parser.add_argument("--minio-secret-key", default=os.getenv("MINIO_SECRET_KEY", ""))
    parser.add_argument("--minio-secure", action="store_true", default=os.getenv("MINIO_SECURE", "false").lower() == "true")
    parser.add_argument("--minio-input-bucket", default=os.getenv("MINIO_INPUT_BUCKET", "hydro-input"))
    parser.add_argument("--minio-output-bucket", default=os.getenv("MINIO_OUTPUT_BUCKET", "hydro-output"))
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    asyncio.run(run_worker(build_parser().parse_args(argv)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
