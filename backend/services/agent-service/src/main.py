from __future__ import annotations

import asyncio
from contextlib import suppress

import grpc

from config import AGENT_GRPC_PORT, NACOS_ENABLED
from discovery import deregister_nacos_instance, register_nacos_instance, send_nacos_beat
from grpc_service import AgentRpcServiceServicer
from generated import agent_pb2_grpc


heartbeat_task: asyncio.Task | None = None
grpc_server: grpc.aio.Server | None = None


async def start_agent_grpc_server() -> None:
    global grpc_server
    # agent-service 只直接暴露 gRPC；HTTP 请求预期由 api-gateway 接入后再转发。
    grpc_server = grpc.aio.server()
    agent_pb2_grpc.add_AgentRpcServiceServicer_to_server(AgentRpcServiceServicer(), grpc_server)
    grpc_server.add_insecure_port(f"[::]:{AGENT_GRPC_PORT}")
    await grpc_server.start()
    print(f"[agent-service] gRPC server started on {AGENT_GRPC_PORT}", flush=True)


async def nacos_registration_loop() -> None:
    # Nacos 容器可能已经 started，但 HTTP API 还没 ready。
    # 这里用后台循环重试，避免启动顺序导致 agent-service 永久查不到。
    retry_seconds = 5
    while True:
        try:
            await register_nacos_instance()
            print("[agent-service] registered to nacos", flush=True)
            while True:
                await send_nacos_beat()
                await asyncio.sleep(retry_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                f"[agent-service] nacos register/heartbeat failed, retry in "
                f"{retry_seconds}s: {exc}",
                flush=True,
            )
            await asyncio.sleep(retry_seconds)


async def on_startup() -> None:
    global heartbeat_task
    await start_agent_grpc_server()
    if NACOS_ENABLED:
        heartbeat_task = asyncio.create_task(nacos_registration_loop())


async def on_shutdown() -> None:
    global heartbeat_task, grpc_server
    if heartbeat_task:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task
        heartbeat_task = None
    if grpc_server:
        await grpc_server.stop(5)
        grpc_server = None
    try:
        await deregister_nacos_instance()
    except Exception as exc:
        print(f"[agent-service] nacos deregister failed: {exc}", flush=True)


async def main() -> None:
    await on_startup()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
