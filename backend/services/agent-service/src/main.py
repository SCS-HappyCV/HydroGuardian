import asyncio
import json
import os
import random
import socket
from typing import Any, Dict, TypedDict

import grpc
import httpx
from langgraph.graph import END, START, StateGraph

import agent_pb2
import agent_pb2_grpc
import case_pb2
import case_pb2_grpc
import grpc_client
import grpc_errors
import file_pb2
import file_pb2_grpc

AGENT_SERVICE_PORT = int(os.getenv("AGENT_SERVICE_PORT", "8081"))
AGENT_GRPC_PORT = int(os.getenv("AGENT_GRPC_PORT", "9091"))
CASE_SERVICE_NAME = os.getenv("CASE_SERVICE_NAME", "case-service")
FILE_SERVICE_NAME = os.getenv("FILE_SERVICE_NAME", "file-service")
CASE_GRPC_ADDR = os.getenv("CASE_GRPC_ADDR", "")
FILE_GRPC_ADDR = os.getenv("FILE_GRPC_ADDR", "")
NACOS_SERVER_ADDR = os.getenv("NACOS_SERVER_ADDR", "localhost:8848")
NACOS_NAMESPACE = os.getenv("NACOS_NAMESPACE", "public")
NACOS_GROUP = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")
NACOS_CLUSTER = os.getenv("NACOS_CLUSTER", "DEFAULT")
NACOS_SERVICE_NAME = os.getenv("NACOS_SERVICE_NAME", "agent-service")
NACOS_IP = os.getenv("NACOS_IP", "")
NACOS_ENABLED = os.getenv("NACOS_ENABLED", "true").lower() == "true"
NACOS_DISCOVERY_CACHE_TTL_SECONDS = float(os.getenv("NACOS_DISCOVERY_CACHE_TTL_SECONDS", "5"))

heartbeat_task: asyncio.Task | None = None
grpc_server: grpc.aio.Server | None = None
service_target_cache: Dict[str, tuple[str, float]] = {}


class AgentState(TypedDict):
    task_text: str
    scene_id: str
    parsed: Dict[str, Any]
    risk_eval: Dict[str, Any]
    recommendation: Dict[str, Any]
    case_result: Dict[str, Any]


def task_parser_node(state: AgentState) -> AgentState:
    text = state["task_text"]
    target = "disturbance"
    if "沟渠" in text:
        target = "ditch"
    elif "陡坡" in text:
        target = "steep_slope"

    state["parsed"] = {
        "targetType": target,
        "constraints": ["near_waterline"] if "近水" in text or "水线" in text else [],
    }
    return state


def risk_node(state: AgentState) -> AgentState:
    score = 0.82 if state["parsed"]["targetType"] != "disturbance" else 0.76
    level = "HIGH" if score >= 0.8 else "MEDIUM"
    state["risk_eval"] = {"score": score, "riskLevel": level}
    return state


def recommendation_node(state: AgentState) -> AgentState:
    level = state["risk_eval"]["riskLevel"]
    action = "立即现场复核并建立临时警戒" if level == "HIGH" else "纳入本周巡检并补充采集"
    state["recommendation"] = {"action": action}
    return state


async def persist_case(state: AgentState) -> Dict[str, Any]:
    request = case_pb2.CreateCaseRequest(
        title=f"{state['parsed']['targetType']} risk case",
        task_text=state["task_text"],
        scene_id=state["scene_id"],
        risk_level=state["risk_eval"]["riskLevel"],
        tags='["langgraph","grpc"]',
    )
    try:
        target = await resolve_grpc_target(CASE_SERVICE_NAME, CASE_GRPC_ADDR)
        async with grpc_client.open_channel(target) as channel:
            stub = case_pb2_grpc.CaseRpcServiceStub(channel)
            reply = await stub.CreateCase(request, timeout=20)
    except Exception as exc:
        raise RuntimeError(f"case gRPC error: {exc}") from exc

    return {
        "caseId": reply.case_id,
        "title": reply.title,
        "taskText": reply.task_text,
        "sceneId": reply.scene_id,
        "status": reply.status,
        "riskLevel": reply.risk_level,
        "assignee": reply.assignee,
        "tags": reply.tags,
        "createdAt": reply.created_at,
    }


async def get_file_info(file_id: str) -> Dict[str, Any]:
    request = file_pb2.GetFileRequest(file_id=file_id)
    target = await resolve_grpc_target(FILE_SERVICE_NAME, FILE_GRPC_ADDR)
    async with grpc_client.open_channel(target) as channel:
        stub = file_pb2_grpc.FileRpcServiceStub(channel)
        reply = await stub.GetFile(request, timeout=10)
    return {
        "fileId": reply.file_id,
        "fileName": reply.file_name,
        "contentType": reply.content_type,
        "size": reply.size,
        "downloadUrl": reply.download_url,
    }


graph_builder = StateGraph(AgentState)
graph_builder.add_node("task_parser", task_parser_node)
graph_builder.add_node("risk", risk_node)
graph_builder.add_node("recommendation_step", recommendation_node)
graph_builder.add_edge(START, "task_parser")
graph_builder.add_edge("task_parser", "risk")
graph_builder.add_edge("risk", "recommendation_step")
graph_builder.add_edge("recommendation_step", END)
graph = graph_builder.compile()


class AgentRpcServiceServicer(agent_pb2_grpc.AgentRpcServiceServicer):
    async def ExecuteTask(self, request, context):
        try:
            init_state: AgentState = {
                "task_text": request.task_text,
                "scene_id": request.scene_id,
                "parsed": {},
                "risk_eval": {},
                "recommendation": {},
                "case_result": {},
            }
            final_state = graph.invoke(init_state)
            case_result = await persist_case(final_state)

            return agent_pb2.ExecuteTaskReply(
                task_text=request.task_text,
                scene_id=request.scene_id,
                target_type=final_state["parsed"].get("targetType", ""),
                risk_score=float(final_state["risk_eval"].get("score", 0.0)),
                risk_level=final_state["risk_eval"].get("riskLevel", ""),
                recommendation_action=final_state["recommendation"].get("action", ""),
                case_id=case_result.get("caseId", ""),
                case_status=case_result.get("status", ""),
            )
        except Exception as exc:
            grpc_errors.internal(context, str(exc))
            return agent_pb2.ExecuteTaskReply()

    async def QueryFile(self, request, context):
        try:
            file_result = await get_file_info(request.file_id)
            return agent_pb2.QueryFileReply(
                file_id=file_result.get("fileId", ""),
                file_name=file_result.get("fileName", ""),
                content_type=file_result.get("contentType", ""),
                size=int(file_result.get("size", 0)),
                download_url=file_result.get("downloadUrl", ""),
            )
        except Exception as exc:
            grpc_errors.internal(context, str(exc))
            return agent_pb2.QueryFileReply()


def resolve_service_ip() -> str:
    if NACOS_IP:
        return NACOS_IP
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def nacos_base_url() -> str:
    if NACOS_SERVER_ADDR.startswith("http://") or NACOS_SERVER_ADDR.startswith("https://"):
        return NACOS_SERVER_ADDR
    return f"http://{NACOS_SERVER_ADDR}"


def pick_instance(instances: list[Dict[str, Any]]) -> Dict[str, Any]:
    enabled_instances = [item for item in instances if item.get("enabled", True)]
    healthy_instances = [item for item in enabled_instances if item.get("healthy", True)]
    candidates = healthy_instances or enabled_instances
    if not candidates:
        raise RuntimeError("Nacos has no enabled instances")

    weighted: list[tuple[Dict[str, Any], float]] = []
    total_weight = 0.0
    for item in candidates:
        try:
            weight = max(float(item.get("weight", 1.0)), 0.0)
        except (TypeError, ValueError):
            weight = 1.0
        weighted.append((item, weight))
        total_weight += weight

    if total_weight <= 0:
        return random.choice(candidates)

    threshold = random.uniform(0.0, total_weight)
    running = 0.0
    for item, weight in weighted:
        running += weight
        if running >= threshold:
            return item
    return weighted[-1][0]


async def resolve_grpc_target(service_name: str, explicit_target: str = "") -> str:
    if explicit_target:
        return explicit_target
    if not NACOS_ENABLED:
        raise RuntimeError(
            f"Nacos discovery is disabled and no direct target is configured for {service_name}"
        )

    now = asyncio.get_running_loop().time()
    cached = service_target_cache.get(service_name)
    if cached and now - cached[1] < NACOS_DISCOVERY_CACHE_TTL_SECONDS:
        return cached[0]

    params = {
        "serviceName": service_name,
        "groupName": NACOS_GROUP,
        "namespaceId": NACOS_NAMESPACE,
        "clusters": NACOS_CLUSTER,
        "healthyOnly": "true",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{nacos_base_url()}/nacos/v1/ns/instance/list", params=params)
        if resp.status_code >= 300:
            raise RuntimeError(
                f"Nacos discover failed for {service_name}: {resp.status_code} {resp.text}"
            )
        payload = resp.json()

    hosts = payload.get("hosts")
    if not isinstance(hosts, list) or not hosts:
        raise RuntimeError(f"Nacos has no instance for service: {service_name}")

    instance = pick_instance(hosts)
    ip = str(instance.get("ip", "")).strip()
    try:
        port = int(instance.get("port", 0))
    except (TypeError, ValueError):
        port = 0

    if not ip or port <= 0:
        raise RuntimeError(f"Nacos returned invalid instance for {service_name}: {instance}")

    target = f"{ip}:{port}"
    service_target_cache[service_name] = (target, now)
    return target


async def register_nacos_instance() -> None:
    if not NACOS_ENABLED:
        return
    params = {
        "ip": resolve_service_ip(),
        "port": AGENT_GRPC_PORT,
        "namespaceId": NACOS_NAMESPACE,
        "serviceName": NACOS_SERVICE_NAME,
        "groupName": NACOS_GROUP,
        "clusterName": NACOS_CLUSTER,
        "weight": 1.0,
        "healthy": "true",
        "enabled": "true",
        "ephemeral": "true",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{nacos_base_url()}/nacos/v1/ns/instance", params=params)
        if resp.status_code >= 300:
            raise RuntimeError(f"Nacos register failed: {resp.status_code} {resp.text}")


async def deregister_nacos_instance() -> None:
    if not NACOS_ENABLED:
        return
    params = {
        "ip": resolve_service_ip(),
        "port": AGENT_GRPC_PORT,
        "namespaceId": NACOS_NAMESPACE,
        "serviceName": NACOS_SERVICE_NAME,
        "groupName": NACOS_GROUP,
        "clusterName": NACOS_CLUSTER,
        "ephemeral": "true",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.delete(f"{nacos_base_url()}/nacos/v1/ns/instance", params=params)


async def send_nacos_beat() -> None:
    if not NACOS_ENABLED:
        return
    beat = {
        "cluster": NACOS_CLUSTER,
        "ip": resolve_service_ip(),
        "port": AGENT_GRPC_PORT,
        "serviceName": NACOS_SERVICE_NAME,
        "scheduled": True,
        "weight": 1.0,
    }
    params = {
        "serviceName": NACOS_SERVICE_NAME,
        "groupName": NACOS_GROUP,
        "namespaceId": NACOS_NAMESPACE,
        "ip": resolve_service_ip(),
        "port": AGENT_GRPC_PORT,
        "beat": json.dumps(beat, ensure_ascii=False),
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.put(f"{nacos_base_url()}/nacos/v1/ns/instance/beat", params=params)


async def nacos_heartbeat_loop() -> None:
    while True:
        try:
            await send_nacos_beat()
        except Exception as exc:
            print(f"[agent-service] nacos heartbeat failed: {exc}")
        await asyncio.sleep(5)


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
