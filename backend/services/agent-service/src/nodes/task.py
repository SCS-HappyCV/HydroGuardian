from __future__ import annotations

from typing import Any, Dict

from state import AgentState, append_trace


def task_parser_node(state: AgentState) -> AgentState:
    text = state["task_text"].strip()
    text_lower = text.lower()

    target = "disturbance"
    if "沟渠" in text or "ditch" in text_lower:
        target = "ditch"
    elif "水线" in text or "waterline" in text_lower:
        target = "waterline"
    elif "陡坡" in text or "steep" in text_lower or "slope" in text_lower:
        target = "steep_slope"
    elif "道路" in text or "road" in text_lower:
        target = "road"

    attributes: list[str] = []
    if "细长" in text or "linear" in text_lower:
        attributes.extend(["thin", "linear"])
    if "裸地" in text or "bare" in text_lower:
        attributes.append("bare")

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
                "evidence": ["geometry"],
            }
        )

    negatives: list[str] = []
    has_negative_cue = "排除" in text or "exclude" in text_lower or "not " in text_lower
    if has_negative_cue and ("道路" in text or "road" in text_lower):
        negatives.extend(["cement road", "dirt road"])

    temporal_keywords = ["变化", "新增", "扩大", "历史", "对比", "前后", "change", "new", "expanded"]
    temporal_intent = any(keyword in text_lower or keyword in text for keyword in temporal_keywords)

    needs_clarification = not text or not state["scene_id"]
    needs_abstain = target == "disturbance" and not relations and not attributes

    state["task_intent"] = {
        "goal": "water_hazard_screening",
        "intent_type": "inspection",
        "target": target,
        "attributes": attributes,
        "relations": relations,
        "negatives": negatives,
        "needs_clarification": needs_clarification,
        "needs_abstain": needs_abstain,
        "priority": "high" if relations or temporal_intent else "medium",
        "temporal_intent": temporal_intent,
        "source_text": text,
    }
    state["status"] = "INTENT_PARSED"
    append_trace(state, "parse_task", "task intent parsed", {"target": target})
    return state
