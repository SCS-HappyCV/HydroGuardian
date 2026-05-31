from __future__ import annotations

from state import AgentState, append_trace


def recommendation_node(state: AgentState) -> AgentState:
    risk = state["risk_cards"][0] if state["risk_cards"] else {}
    risk_level = str(risk.get("risk_level", "REVIEW_REQUIRED"))
    risk_type = str(risk.get("risk_type", "water_hazard_screening_risk"))

    if risk_level == "HIGH":
        action = "优先安排人工复核疑似高风险区域，并同步保留 3D 证据链"
        suggestion = "核查候选区域是否与水线连通，确认是否存在新增扰动或工程隐患"
    elif risk_level == "MEDIUM":
        action = "纳入近期巡检计划，并补充采集局部高分辨率影像"
        suggestion = "结合候选区域几何形态、排除项和现场照片二次确认"
    elif risk_level == "LOW":
        action = "记录为低风险线索，后续巡检中持续观察"
        suggestion = "保持证据包和任务 trace，暂不生成紧急处置动作"
    else:
        action = "转人工复核，当前证据不足以自动给出风险等级"
        suggestion = "检查 3D 服务执行结果、输入张量完整性、拒答信号和 no-target 信号"

    recommendation = {
        "recommendation_id": "rec_001",
        "risk_card_id": "risk_001",
        "recommended_action": action,
        "review_suggestion": suggestion,
        "supplementary_collection": ["局部高分辨率影像", "现场复核照片"],
        "confidence_note": "该建议基于 3D EvidencePack 和可选变化检测信号，不替代最终工程判定",
    }
    work_order = {
        "work_order_id": "wo_001",
        "risk_card_id": "risk_001",
        "status": "todo",
        "assignee": "field_team_a" if risk_level in {"HIGH", "REVIEW_REQUIRED"} else "",
        "deadline": "",
        "summary": f"复核 {risk_type} 线索",
        "closure_status": "open",
    }

    state["recommendation_cards"] = [recommendation]
    state["work_orders"] = [work_order]
    state["status"] = "RECOMMENDATION_READY"
    append_trace(state, "generate_recommendation", "recommendation and work order generated")
    return state
