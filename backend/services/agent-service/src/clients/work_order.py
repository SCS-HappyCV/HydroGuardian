# case-service 工单客户端。
# 本模块负责把 agent-service 的工单草稿提交给 case-service，并转换真实工单响应。

from __future__ import annotations

import json
from typing import Any, Dict, Iterable

from config import CASE_GRPC_TIMEOUT_SECONDS
from generated import case_pb2


# 安全序列化 JSON 字段，避免证据摘要中出现不可直接编码的对象。
def _json_dump(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return "[]"


# 安全解析 JSON 字段；解析失败时返回空列表，保持工单结构稳定。
def _json_load(raw_json: str) -> Any:
    if not raw_json:
        return []
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        return []


# 将工单草稿转换为 case-service CreateWorkOrderRequest。
def build_create_work_order_request(case_id: str, draft: Dict[str, Any]) -> case_pb2.CreateWorkOrderRequest:
    evidence_summary = draft.get("evidence_summary")
    return case_pb2.CreateWorkOrderRequest(
        case_id=case_id,
        risk_card_id=str(draft.get("risk_card_id", "")),
        risk_type=str(draft.get("risk_type", "")),
        risk_level=str(draft.get("risk_level", "")),
        title=str(draft.get("title", "")),
        summary=str(draft.get("summary", "")),
        recommended_action=str(draft.get("recommended_action", "")),
        assignee=str(draft.get("assignee", "")),
        status=str(draft.get("status", "TODO")),
        deadline=str(draft.get("deadline", "")),
        evidence_summary_json=_json_dump(evidence_summary if isinstance(evidence_summary, list) else []),
        schema_version="case_work_order.v1",
    )


# 将 case-service WorkOrderReply 转成 agent-service 内部字典。
def work_order_reply_to_dict(reply: case_pb2.WorkOrderReply) -> Dict[str, Any]:
    return {
        "schema_version": reply.schema_version,
        "work_order_id": reply.work_order_id,
        "case_id": reply.case_id,
        "risk_card_id": reply.risk_card_id,
        "risk_type": reply.risk_type,
        "risk_level": reply.risk_level,
        "title": reply.title,
        "summary": reply.summary,
        "recommended_action": reply.recommended_action,
        "status": reply.status,
        "assignee": reply.assignee,
        "deadline": reply.deadline,
        "closure_note": reply.closure_note,
        "closure_status": "closed" if reply.status == "CLOSED" else "open",
        "evidence_summary": _json_load(reply.evidence_summary_json),
        "created_at": reply.created_at,
        "updated_at": reply.updated_at,
    }


# 创建单个真实工单，并返回标准字典。
async def create_case_work_order(
    stub: Any,
    case_id: str,
    draft: Dict[str, Any],
    timeout: float = CASE_GRPC_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    request = build_create_work_order_request(case_id, draft)
    reply = await stub.CreateWorkOrder(request, timeout=timeout)
    return work_order_reply_to_dict(reply)


# 批量创建真实工单；当前通常只有一条，但接口按列表设计，方便未来 Top-K 风险扩展。
async def create_case_work_orders(
    stub: Any,
    case_id: str,
    drafts: Iterable[Dict[str, Any]],
    timeout: float = CASE_GRPC_TIMEOUT_SECONDS,
) -> list[Dict[str, Any]]:
    created: list[Dict[str, Any]] = []
    for draft in drafts:
        # 每条工单独立提交，便于后续按 Top-K 风险逐条记录结果。
        created.append(await create_case_work_order(stub, case_id, draft, timeout))
    return created
