from __future__ import annotations

from typing import Any, Dict, TypedDict


class AgentState(TypedDict):
    case_id: str
    task_id: str
    task_text: str
    scene_id: str
    sample_id: str
    task_intent: Dict[str, Any]
    program_bundle: Dict[str, Any]
    selected_program: Dict[str, Any]
    scene_tensor_sample: Dict[str, Any]
    raw_executor_output: Dict[str, Any]
    evidence_pack: Dict[str, Any]
    change_pack: Dict[str, Any]
    risk_cards: list[Dict[str, Any]]
    recommendation_cards: list[Dict[str, Any]]
    work_orders: list[Dict[str, Any]]
    case_result: Dict[str, Any]
    status: str
    errors: list[Dict[str, Any]]
    trace: list[Dict[str, Any]]


def append_trace(state: AgentState, stage: str, message: str, data: Dict[str, Any] | None = None) -> None:
    item: Dict[str, Any] = {"stage": stage, "message": message}
    if data:
        item["data"] = data
    state["trace"].append(item)


def append_error(state: AgentState, stage: str, message: str, data: Dict[str, Any] | None = None) -> None:
    item: Dict[str, Any] = {"stage": stage, "message": message}
    if data:
        item["data"] = data
    state["errors"].append(item)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if isinstance(value, list):
            return as_float(value[0] if value else default, default)
        return float(value)
    except (TypeError, ValueError):
        return default


def failure_evidence_pack(reason: str) -> Dict[str, Any]:
    return {
        "status": "execution_failed",
        "target_hit": False,
        "review_required": True,
        "confidence": 0.0,
        "selected_candidate_idx": None,
        "selected_candidate_is_no_target": True,
        "selected_verifier_score": 0.0,
        "posterior_no_target_mass": 1.0,
        "abstain_probability": 1.0,
        "candidate_regions": [],
        "evidence_summary": [reason],
        "raw_trace": {"failure_reason": reason},
    }
