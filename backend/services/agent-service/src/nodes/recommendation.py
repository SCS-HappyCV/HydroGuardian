# 建议卡生成节点。
# 本节点只负责把风险卡转换为处置建议，不再生成工单 ID 或工单状态。

from __future__ import annotations

from state import AgentState, append_trace


# 根据风险等级生成建议动作和复核说明。
def _recommendation_text(risk_level: str) -> tuple[str, str]:
    if risk_level == "HIGH":
        return (
            "优先安排人工复核疑似高风险区域，并同步保留 3D 证据链",
            "核查候选区域是否与水线连通，确认是否存在新增扰动或工程隐患",
        )
    if risk_level == "MEDIUM":
        return (
            "纳入近期巡检计划，并补充采集局部高分辨率影像",
            "结合候选区域几何形态、排除项和现场照片二次确认",
        )
    if risk_level == "LOW":
        return (
            "记录为低风险线索，后续巡检中持续观察",
            "保持证据包和任务 trace，暂不生成紧急处置动作",
        )
    return (
        "转人工复核，当前证据不足以自动给出风险等级",
        "检查 3D 服务执行结果、输入张量完整性、拒答信号和 no-target 信号",
    )


# 生成 recommendation card，并把工单创建留给独立节点处理。
def recommendation_node(state: AgentState) -> AgentState:
    risk = state["risk_cards"][0] if state["risk_cards"] else {}
    risk_level = str(risk.get("risk_level", "REVIEW_REQUIRED"))
    action, suggestion = _recommendation_text(risk_level)

    recommendation = {
        "recommendation_id": "rec_primary",
        "risk_card_id": str(risk.get("risk_card_id", "risk_primary")),
        "recommended_action": action,
        "review_suggestion": suggestion,
        "supplementary_collection": ["局部高分辨率影像", "现场复核照片"],
        "confidence_note": "该建议基于 3D EvidencePack 和可选变化检测信号，不替代最终工程判定",
    }

    state["recommendation_cards"] = [recommendation]
    state["status"] = "RECOMMENDATION_READY"
    append_trace(
        state,
        "generate_recommendation",
        "recommendation card generated",
        {"risk_level": risk_level, "recommendation_id": recommendation["recommendation_id"]},
    )
    return state
