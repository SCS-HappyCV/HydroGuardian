from __future__ import annotations

import json
from typing import Any, Dict

import grpc_client
from config import CASE_GRPC_ADDR, CASE_SERVICE_NAME, FILE_GRPC_ADDR, FILE_SERVICE_NAME
from discovery import resolve_grpc_target
from generated import case_pb2, case_pb2_grpc, file_pb2, file_pb2_grpc
from state import AgentState


async def persist_case(state: AgentState) -> Dict[str, Any]:
    risk = state["risk_cards"][0] if state["risk_cards"] else {}
    target = state["task_intent"].get("target", "water_hazard")
    tags = {
        "tags": ["langgraph", "hydro-program3d", "agent-service"],
        "riskType": risk.get("risk_type"),
        "reviewRequired": risk.get("review_required"),
        "evidenceStatus": state["evidence_pack"].get("status"),
    }
    request = case_pb2.CreateCaseRequest(
        title=f"{target} risk case",
        task_text=state["task_text"],
        scene_id=state["scene_id"],
        risk_level=str(risk.get("risk_level", "REVIEW_REQUIRED")),
        assignee=state["work_orders"][0].get("assignee", "") if state["work_orders"] else "",
        tags=json.dumps(tags, ensure_ascii=False),
    )
    target_addr = await resolve_grpc_target(CASE_SERVICE_NAME, CASE_GRPC_ADDR)
    async with grpc_client.open_channel(target_addr) as channel:
        stub = case_pb2_grpc.CaseRpcServiceStub(channel)
        reply = await stub.CreateCase(request, timeout=20)

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
