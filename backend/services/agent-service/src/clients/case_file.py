# case-service 和 file-service 客户端。
# case 持久化会构建 agent_result 快照，并把完整 JSON 交给 case-service 落到数据库。

from __future__ import annotations

import json
from typing import Any, Dict

from case_persistence import build_agent_result_snapshot, build_case_tags_payload, parse_case_tags
from clients.work_order import create_case_work_orders
from config import CASE_GRPC_ADDR, CASE_SERVICE_NAME
from discovery import resolve_grpc_target
from generated import case_pb2, case_pb2_grpc
import grpc_client
from state import AgentState, append_error, append_trace


# 根据最终 AgentState 构造 CreateCaseRequest。
def build_create_case_request(state: AgentState, snapshot: Dict[str, Any]) -> case_pb2.CreateCaseRequest:
    risk = state["risk_cards"][0] if state["risk_cards"] else {}
    target = state["task_intent"].get("target", "water_hazard")
    tags_payload = build_case_tags_payload(snapshot)
    agent_result_json = json.dumps(snapshot, ensure_ascii=False)
    return case_pb2.CreateCaseRequest(
        title=f"{target} risk case",
        task_text=state["task_text"],
        scene_id=state["scene_id"],
        risk_level=str(risk.get("risk_level", "REVIEW_REQUIRED")),
        assignee=state["work_orders"][0].get("assignee", "") if state["work_orders"] else "",
        tags=json.dumps(tags_payload, ensure_ascii=False),
        agent_result_json=agent_result_json,
    )


# 根据最终快照构造 UpdateCaseAgentResultRequest。
def build_update_case_agent_result_request(case_id: str, snapshot: Dict[str, Any]) -> case_pb2.UpdateCaseAgentResultRequest:
    return case_pb2.UpdateCaseAgentResultRequest(
        case_id=case_id,
        agent_result_json=json.dumps(snapshot, ensure_ascii=False),
    )


# 将 case-service 返回的 proto 响应转换为 agent-service 内部字典。
def case_reply_to_dict(reply: case_pb2.CaseReply, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    parsed_tags = parse_case_tags(reply.tags)
    agent_result_json = reply.agent_result_json
    agent_result_saved = bool(agent_result_json)
    return {
        "caseId": reply.case_id,
        "title": reply.title,
        "taskText": reply.task_text,
        "sceneId": reply.scene_id,
        "status": reply.status,
        "riskLevel": reply.risk_level,
        "assignee": reply.assignee,
        "tags": reply.tags,
        "tagsParsed": parsed_tags,
        "createdAt": reply.created_at,
        "persistenceStatus": "success" if agent_result_saved else "partial",
        "persistenceError": "" if agent_result_saved else "case saved but agent_result_json was not returned",
        "agentResultSaved": agent_result_saved,
        "agentResultJson": agent_result_json,
        "agentResultSnapshot": snapshot,
        "agentResultSnapshotSchema": snapshot.get("schema_version", ""),
    }


# 构造持久化失败时也可返回给上游的 case_result。
def build_persistence_failure_result(state: AgentState, error: Exception) -> Dict[str, Any]:
    snapshot = build_agent_result_snapshot(state)
    return {
        "caseId": "",
        "title": "",
        "taskText": state.get("task_text", ""),
        "sceneId": state.get("scene_id", ""),
        "status": "",
        "riskLevel": "",
        "assignee": "",
        "tags": "",
        "tagsParsed": {},
        "createdAt": "",
        "persistenceStatus": "failed",
        "persistenceError": str(error),
        "agentResultSaved": False,
        "agentResultJson": "",
        "agentResultSnapshot": snapshot,
        "agentResultSnapshotSchema": snapshot.get("schema_version", ""),
    }


# 将 agent 执行结果持久化到 case-service。
async def persist_case(state: AgentState) -> Dict[str, Any]:
    initial_snapshot = build_agent_result_snapshot(state)
    request = build_create_case_request(state, initial_snapshot)
    append_trace(
        state,
        "persist_case.snapshot",
        "initial agent result snapshot built",
        {
            "schema_version": initial_snapshot.get("schema_version"),
            "trace_count": len(initial_snapshot.get("trace") or []),
            "error_count": len(initial_snapshot.get("errors") or []),
            "tags_payload_bytes": len(request.tags.encode("utf-8")),
            "agent_result_json_bytes": len(request.agent_result_json.encode("utf-8")),
        },
    )

    target_addr = await resolve_grpc_target(CASE_SERVICE_NAME, CASE_GRPC_ADDR)
    async with grpc_client.open_channel(target_addr) as channel:
        stub = case_pb2_grpc.CaseRpcServiceStub(channel)
        reply = await stub.CreateCase(request, timeout=20)
        state["case_id"] = reply.case_id

        work_order_error = ""
        update_snapshot_error = ""
        drafts = state.get("work_orders") or []
        if drafts:
            try:
                created_work_orders = await create_case_work_orders(stub, reply.case_id, drafts)
                state["work_orders"] = created_work_orders
                append_trace(
                    state,
                    "persist_work_order",
                    "case work orders persisted",
                    {
                        "case_id": reply.case_id,
                        "work_order_count": len(created_work_orders),
                        "work_order_ids": [item.get("work_order_id", "") for item in created_work_orders],
                    },
                )
            except Exception as exc:
                # 工单失败时保留 case 主结果，并把错误写入 trace/errors 供前端排障。
                work_order_error = str(exc)
                append_error(state, "persist_work_order", work_order_error)

        final_snapshot = build_agent_result_snapshot(state)
        try:
            reply = await stub.UpdateCaseAgentResult(
                build_update_case_agent_result_request(reply.case_id, final_snapshot),
                timeout=20,
            )
            append_trace(
                state,
                "persist_case.snapshot",
                "final agent result snapshot updated",
                {
                    "case_id": reply.case_id,
                    "work_order_count": len(state.get("work_orders") or []),
                    "agent_result_json_bytes": len(json.dumps(final_snapshot, ensure_ascii=False).encode("utf-8")),
                },
            )
        except Exception as exc:
            # 快照回写失败不抹掉已经创建的 case/work-order，但需要标记为 partial。
            update_snapshot_error = str(exc)
            append_error(state, "persist_case.snapshot", update_snapshot_error)

    result = case_reply_to_dict(reply, final_snapshot)
    partial_errors = [message for message in [work_order_error, update_snapshot_error] if message]
    if partial_errors:
        result["persistenceStatus"] = "partial"
        result["persistenceError"] = "; ".join(partial_errors)
    append_trace(
        state,
        "persist_case",
        "case persisted",
        {
            "case_id": result.get("caseId"),
            "status": result.get("status"),
            "persistence_status": result.get("persistenceStatus"),
            "agent_result_saved": result.get("agentResultSaved"),
            "work_order_count": len(state.get("work_orders") or []),
        },
    )
    return result
