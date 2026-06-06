# ExecuteTask 响应组装器。
# 本模块把 gRPC 响应结构和图执行逻辑拆开，让服务入口主要保留编排逻辑。

from __future__ import annotations

import json
from typing import Any, Dict, Iterable

from generated import agent_pb2
from state import AgentState


# 将可选的 trace/error 数据序列化成 proto 友好的字符串。
def _json_dump(value: Any) -> str:
    if value is None:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return str(value)


# 将 AgentState.trace 字典转换成 gRPC trace item。
def _trace_items(events: Iterable[Dict[str, Any]]) -> list[agent_pb2.AgentTraceItem]:
    return [
        agent_pb2.AgentTraceItem(
            stage=str(event.get("stage", "")),
            message=str(event.get("message", "")),
            data_json=_json_dump(event.get("data")),
        )
        for event in events
    ]


# 将 AgentState.errors 字典转换成 gRPC error item。
def _error_items(events: Iterable[Dict[str, Any]]) -> list[agent_pb2.AgentErrorItem]:
    return [
        agent_pb2.AgentErrorItem(
            stage=str(event.get("stage", "")),
            message=str(event.get("message", "")),
            data_json=_json_dump(event.get("data")),
        )
        for event in events
    ]


# 将证据、风险卡和终态状态合并成一个 review_required 标记。
def _review_required(state: AgentState) -> bool:
    evidence = state.get("evidence_pack") or {}
    risk = state["risk_cards"][0] if state.get("risk_cards") else {}
    status = state.get("status", "")
    return bool(
        risk.get("review_required")
        or evidence.get("review_required")
        or status in {"REVIEW_REQUIRED", "FAILED", "ABSTAINED"}
    )


# 根据最终图状态和 case 持久化结果构建对外 ExecuteTaskReply。
def build_execute_task_reply(
    *,
    request: Any,
    state: AgentState,
    case_result: Dict[str, Any],
) -> agent_pb2.ExecuteTaskReply:
    risk = state["risk_cards"][0] if state.get("risk_cards") else {}
    recommendation = state["recommendation_cards"][0] if state.get("recommendation_cards") else {}
    intent = state.get("task_intent") or {}
    evidence = state.get("evidence_pack") or {}
    case_result = case_result or {}
    trace = state.get("trace") or []
    errors = state.get("errors") or []

    # trace 可能包含模型和服务诊断信息，因此仅在调用方开启 debug 时返回；
    # errors 体量较小且便于排障，可以始终返回。
    visible_trace = trace if bool(getattr(request, "debug", False)) else []

    return agent_pb2.ExecuteTaskReply(
        task_text=request.task_text,
        scene_id=request.scene_id,
        target_type=str(intent.get("target", "")),
        risk_score=float(risk.get("risk_score", 0.0)),
        risk_level=str(risk.get("risk_level", "")),
        recommendation_action=str(recommendation.get("recommended_action", "")),
        case_id=str(case_result.get("caseId", "")),
        case_status=str(case_result.get("status", "")),
        execution_status=str(state.get("status", "")),
        parser_source=str(intent.get("parser_source", "")),
        evidence_status=str(evidence.get("status", "")),
        review_required=_review_required(state),
        trace=_trace_items(visible_trace),
        errors=_error_items(errors),
        trace_total=len(trace),
        error_count=len(errors),
        case_persistence_status=str(case_result.get("persistenceStatus", "")),
        case_persistence_error=str(case_result.get("persistenceError", "")),
        work_orders_json=_json_dump(state.get("work_orders") or []),
    )
