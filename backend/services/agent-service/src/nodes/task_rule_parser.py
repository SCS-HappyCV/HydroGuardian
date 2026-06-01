from __future__ import annotations

from typing import Any, Dict

from state import AgentState

from .task_contract import normalize_intent, normalize_temporal_intent

#放规则回退解析逻辑
def parse_task_with_rules(state: AgentState) -> Dict[str, Any]:
    text = state["task_text"].strip()
    text_lower = text.lower()

    target = "disturbance"
    attributes: list[str] = []
    if "沟渠" in text or "ditch" in text_lower:
        target = "ditch"
    elif "水线" in text or "waterline" in text_lower:
        target = "waterline"
    elif "陡坡" in text or "steep" in text_lower or "slope" in text_lower:
        target = "slope"
        attributes.append("steep")
    elif "道路" in text or "road" in text_lower:
        target = "road"

    if "细长" in text or "linear" in text_lower:
        attributes.extend(["thin", "linear"])
    if "裸地" in text or "bare" in text_lower:
        attributes.append("bare_ground")

    relations: list[Dict[str, Any]] = []
    if "近水" in text or "水线" in text or "waterline" in text_lower or "near water" in text_lower:
        if target == "waterline" and ("沟渠" in text or "ditch" in text_lower):
            reference = "ditch"
        else:
            reference = "waterline"
        relations.append(
            {
                "type": "near",
                "reference": reference,
                "distance_m": 5.0,
                "margin_m": None,
                "evidence": ["geometry"],
            }
        )

    negatives: list[str] = []
    has_negative_cue = "排除" in text or "exclude" in text_lower or "not " in text_lower
    if has_negative_cue and ("道路" in text or "road" in text_lower):
        negatives.extend(["cement road", "dirt road"])

    payload = {
        "goal": "water_hazard_screening",
        "intent_type": "inspection",
        "target": target,
        "attributes": attributes,
        "relations": relations,
        "negatives": negatives,
        "needs_clarification": False,
        "clarification_question": "",
        "needs_abstain": False,
        "abstain_reason": "",
        "priority": "high" if relations or normalize_temporal_intent(text) else "medium",
        "temporal_intent": normalize_temporal_intent(text),
    }
    return normalize_intent(payload, state, parser_source="rule_fallback")
