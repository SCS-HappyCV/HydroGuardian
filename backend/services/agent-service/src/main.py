from __future__ import annotations

import asyncio

import grpc

from config import AGENT_GRPC_PORT
from discovery import deregister_nacos_instance, nacos_heartbeat_loop, register_nacos_instance
from grpc_service import AgentRpcServiceServicer
from generated import agent_pb2_grpc


heartbeat_task: asyncio.Task | None = None
grpc_server: grpc.aio.Server | None = None


async def start_agent_grpc_server() -> None:
    global grpc_server
    grpc_server = grpc.aio.server()
    agent_pb2_grpc.add_AgentRpcServiceServicer_to_server(AgentRpcServiceServicer(), grpc_server)
    grpc_server.add_insecure_port(f"[::]:{AGENT_GRPC_PORT}")
    await grpc_server.start()
    print(f"[agent-service] gRPC server started on {AGENT_GRPC_PORT}")


async def on_startup() -> None:
    global heartbeat_task
    await start_agent_grpc_server()
    try:
        await register_nacos_instance()
        heartbeat_task = asyncio.create_task(nacos_heartbeat_loop())
        print("[agent-service] registered to nacos")
    except Exception as exc:
        print(f"[agent-service] nacos register failed: {exc}")


async def on_shutdown() -> None:
    global heartbeat_task, grpc_server
    if heartbeat_task:
        heartbeat_task.cancel()
        heartbeat_task = None
    if grpc_server:
        await grpc_server.stop(5)
        grpc_server = None
    try:
        await deregister_nacos_instance()
    except Exception as exc:
        print(f"[agent-service] nacos deregister failed: {exc}")


async def main() -> None:
    await on_startup()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
