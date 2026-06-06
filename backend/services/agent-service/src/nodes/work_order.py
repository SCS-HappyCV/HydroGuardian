# 工单草稿生成节点。
# 本节点只生成待落库的工单草稿，真实 work_order_id 由 case-service 在持久化阶段生成。

from __future__ import annotations

from typing import Any, Dict

from state import AgentState, append_trace


# 根据风险等级选择默认负责人。
def _default_assignee(risk_level: str) -> str:
    return "field_team_a" if risk_level in {"HIGH", "REVIEW_REQUIRED"} else ""


# 根据风险等级和负责人推导初始工单状态。
def _initial_status(risk_level: str, assignee: str) -> str:
    if assignee:
        return "ASSIGNED"
    if risk_level in {"HIGH", "REVIEW_REQUIRED"}:
        return "TODO"
    return "TODO"


# 从证据包中提取可写入工单的轻量证据摘要。
def _evidence_summary(evidence_pack: Dict[str, Any]) -> list[Any]:
    summary = evidence_pack.get("evidence_summary")
    return summary if isinstance(summary, list) else []


# 生成工单草稿；后续 persist_case 会调用 case-service 创建真实工单。
def work_order_node(state: AgentState) -> AgentState:
    risk = state["risk_cards"][0] if state["risk_cards"] else {}
    recommendation = state["recommendation_cards"][0] if state["recommendation_cards"] else {}
    evidence_pack = state.get("evidence_pack") or {}
    risk_level = str(risk.get("risk_level", "REVIEW_REQUIRED"))
    risk_type = str(risk.get("risk_type", "water_hazard_screening_risk"))
    assignee = _default_assignee(risk_level)

    # 草稿阶段不写 work_order_id；真实 ID 在 case-service CreateWorkOrder 中生成。
    work_order = {
        "schema_version": "agent_work_order_draft.v1",
        "work_order_id": "",
        "case_id": "",
        "risk_card_id": str(risk.get("risk_card_id", "risk_primary")),
        "risk_type": risk_type,
        "risk_level": risk_level,
        "title": f"复核 {risk_type} 线索",
        "summary": f"针对场景 {state.get('scene_id', '')} 的 {risk_level} 风险线索执行现场复核",
        "recommended_action": str(recommendation.get("recommended_action", "")),
        "status": _initial_status(risk_level, assignee),
        "assignee": assignee,
        "deadline": "",
        "closure_note": "",
        "evidence_summary": _evidence_summary(evidence_pack),
        "closure_status": "open",
    }

    state["work_orders"] = [work_order]
    state["status"] = "WORK_ORDER_READY"
    append_trace(
        state,
        "create_work_order",
        "work order draft generated",
        {
            "risk_level": risk_level,
            "status": work_order["status"],
            "assignee": work_order["assignee"],
        },
    )
    return state
