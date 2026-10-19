from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional, Sequence

from hydro_remote_agent.runtime import load_expert_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.websocket_protocol import make_message, parse_message, sign_worker_payload


async def run_smoke(args: argparse.Namespace) -> int:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("Smoke test requires websockets") from exc
    registry = load_tool_registry(args.registry)
    runtime = load_expert_runtime(args.runtime, registry, work_dir=args.work_dir)
    worker_id = args.worker_id or f"smoke-worker-{secrets.token_hex(4)}"
    timestamp = int(time.time())
    nonce = secrets.token_hex(16)
    register = make_message(
        "register", worker_id=worker_id, worker_version="e2e-smoke",
        capabilities=[args.tool], gpus=[], auth_timestamp=str(timestamp), auth_nonce=nonce,
        auth_signature=sign_worker_payload(worker_id, timestamp, nonce, args.worker_secret)
        if args.worker_secret else "",
    )
    task_id = f"smoke-task-{secrets.token_hex(6)}"
    arguments = json.loads(args.arguments)
    if not isinstance(arguments, dict):
        raise ValueError("--arguments must be a JSON object")
    job_payload = {
        "request_id": task_id,
        "query": "end-to-end smoke test",
        "assets": {},
        "planned_request": {
            "schema_version": "1.0", "request_id": task_id, "intent": "smoke",
            "action": {"type": "direct_answer", "answer": "smoke"},
            "expected_output": {"type": "text", "coordinate_space": "none"},
        },
    }
    try:
        async with websockets.connect(args.agent_ws_url, ping_interval=15, ping_timeout=30) as socket:
            await socket.send(json.dumps(register))
            registered = parse_message(await socket.recv())
            if registered["type"] != "registered":
                raise RuntimeError(f"Worker registration failed: {registered}")
            create_request = urllib.request.Request(
                f"{args.agent_http_url.rstrip('/')}/v1/jobs",
                data=json.dumps(job_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(create_request, timeout=30) as response:
                created_job = json.loads(response.read().decode("utf-8"))
            job_id = str(created_job["job_id"])
            async def invoke_agent() -> dict[str, Any]:
                payload = json.dumps({
                    "invocation_id": task_id,
                    "job_id": job_id,
                    "arguments": arguments,
                    "timeout_seconds": args.timeout_seconds,
                }).encode("utf-8")
                request = urllib.request.Request(
                    f"{args.agent_http_url.rstrip('/')}/internal/tools/{args.tool}/invoke",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                def call() -> dict[str, Any]:
                    with urllib.request.urlopen(request, timeout=args.timeout_seconds + 30) as response:
                        return json.loads(response.read().decode("utf-8"))
                return await asyncio.to_thread(call)

            invoke_task = asyncio.create_task(invoke_agent())
            while True:
                receive_task = asyncio.create_task(socket.recv())
                done, _ = await asyncio.wait(
                    {receive_task, invoke_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if invoke_task in done:
                    receive_task.cancel()
                    await invoke_task
                    raise RuntimeError("Agent invocation completed before dispatching a task")
                message = parse_message(await receive_task)
                if message["type"] == "cancel":
                    await socket.send(json.dumps(make_message(
                        "cancel_ack", worker_id=worker_id, task_id=task_id
                    )))
                    continue
                if message["type"] != "task":
                    continue
                task_id = str(message["task_id"])
                await socket.send(json.dumps(make_message(
                    "task_ack", worker_id=worker_id, task_id=task_id
                )))
                await socket.send(json.dumps(make_message(
                    "progress", worker_id=worker_id, task_id=task_id, job_id=job_id,
                    tool=args.tool, progress=0.0, phase="smoke_started"
                )))
                runtime.prepare(args.tool)
                result = await asyncio.to_thread(runtime.invoke, args.tool, arguments, task_id)
                result_payload = result.to_dict()
                await socket.send(json.dumps(make_message(
                    "completed", worker_id=worker_id, task_id=task_id, job_id=job_id,
                    tool=args.tool, result=result_payload, produced_artifacts=[]
                )))
                response = await invoke_task
                print(json.dumps({"status": "succeeded", "task_id": task_id,
                                  "tool": args.tool, "result": response}, ensure_ascii=False, indent=2))
                return 0
    finally:
        runtime.shutdown()


def build_parser() -> argparse.ArgumentParser:
    package_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="End-to-end WebSocket expert smoke test.")
    parser.add_argument("--agent-ws-url", default="ws://127.0.0.1:18080/internal/workers/ws")
    parser.add_argument("--agent-http-url", default="http://127.0.0.1:18080")
    parser.add_argument("--registry", default=str(package_root / "configs" / "tool_registry.yaml"))
    parser.add_argument("--runtime", default=str(package_root / "configs" / "expert_runtime.yaml"))
    parser.add_argument("--work-dir", default=str(package_root / "runs" / "e2e_smoke"))
    parser.add_argument("--worker-id")
    parser.add_argument("--worker-secret", default="")
    parser.add_argument("--job-id", default="smoke-job")
    parser.add_argument("--tool", default="geometry_relation_analysis")
    parser.add_argument("--arguments", default=json.dumps({
        "point_cloud_path": "smoke_points.txt",
    }))
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    return asyncio.run(run_smoke(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
