from __future__ import annotations

from state import AgentState, append_trace, as_float, failure_evidence_pack


def infer_risk_type(state: AgentState) -> str:
    # risk_type 主要是给业务层一个更直观的风险名称，
    # 不直接参与底层模型执行。
    target = state["task_intent"].get("target")
    attributes = set(state["task_intent"].get("attributes") or [])
    has_water_relation = any(
        relation.get("reference") == "waterline"
        for relation in state["selected_program"].get("relations", [])
    )
    if target == "ditch" and has_water_relation:
        return "near_waterline_ditch_risk"
    if target in {"road", "cement road", "dirt road"} and has_water_relation:
        return "near_waterline_road_disturbance_risk"
    if target == "steep_slope" or (target == "slope" and "steep" in attributes):
        return "steep_slope_bare_land_risk"
    if state["task_intent"].get("temporal_intent"):
        return "change_review_required_risk"
    return "water_hazard_screening_risk"


def risk_assessment_node(state: AgentState) -> AgentState:
    # 这里故意只消费 EvidencePack / ChangePack，
    # 不再回头直接读原始模型 tensor，保持业务层输入稳定。
    evidence = state["evidence_pack"] or failure_evidence_pack("missing evidence")
    change = state["change_pack"] or {}

    if evidence.get("status") != "success":
        # 只要 3D 证据没有成功产出，就不要硬给自动高风险结论。
        risk_score = 0.0
        risk_level = "REVIEW_REQUIRED"
        trigger_evidence = list(evidence.get("evidence_summary") or ["3D evidence unavailable"])
    else:
        confidence = as_float(evidence.get("confidence"))
        verifier = as_float(evidence.get("selected_verifier_score"))
        no_target_mass = as_float(evidence.get("posterior_no_target_mass"))
        abstain_probability = as_float(evidence.get("abstain_probability"))
        regions = evidence.get("candidate_regions") or []
        # 第一版先用可解释的规则加权，便于和 EvidencePack 对齐排查。
        # 后面真要引入学习式风险评分，也建议先从这里替换。
        relation_bonus = 0.12 if state["selected_program"].get("relations") else 0.0
        attribute_bonus = 0.08 if state["selected_program"].get("attributes") else 0.0
        geometry_bonus = 0.08 if regions else 0.0
        change_bonus = 0.10 if change.get("status") == "success" else 0.0
        negative_penalty = 0.05 if state["selected_program"].get("negative_label_ids") else 0.0

        risk_score = (
            0.45 * confidence
            + 0.25 * verifier
            + relation_bonus
            + attribute_bonus
            + geometry_bonus
            + change_bonus
            - 0.25 * no_target_mass
            - 0.20 * abstain_probability
            - negative_penalty
        )
        risk_score = max(0.0, min(1.0, risk_score))

        review_required = bool(evidence.get("review_required")) or bool(change.get("review_required"))
        if review_required and risk_score < 0.80:
            risk_level = "REVIEW_REQUIRED"
        elif risk_score >= 0.80:
            risk_level = "HIGH"
        elif risk_score >= 0.55:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        trigger_evidence = list(evidence.get("evidence_summary") or [])
        if change.get("status") == "success":
            trigger_evidence.append("change detector generated a temporal change mask")
        if not trigger_evidence:
            trigger_evidence.append("evidence pack compiled without textual summary")

    # 目前默认只拿第一个区域当主风险区域。
    # 如果后面要支持 Top-K 风险点，这里和上游 evidence 都要一起扩。
    region_id = ""
    regions = evidence.get("candidate_regions") or []
    if regions and isinstance(regions[0], dict):
        region_id = str(regions[0].get("region_id", ""))

    risk_card = {
        "risk_type": infer_risk_type(state),
        "risk_level": risk_level,
        "risk_score": round(risk_score, 4),
        "priority_rank": 1,
        "review_required": risk_level == "REVIEW_REQUIRED" or bool(evidence.get("review_required")),
        "trigger_evidence": trigger_evidence,
        "candidate_region_id": region_id,
    }
    state["risk_cards"] = [risk_card]
    state["status"] = "RISK_READY"
    append_trace(state, "assess_risk", "risk card generated", {"risk_level": risk_level})
    return state
