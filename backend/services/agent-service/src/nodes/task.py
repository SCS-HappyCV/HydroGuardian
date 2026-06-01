from __future__ import annotations

from config import TASK_PARSER_BACKEND, TASK_PARSER_FALLBACK_TO_RULE
from state import AgentState, append_error, append_trace

from .task_contract import normalize_intent, normalize_temporal_intent
from .task_openai_parser import parse_task_with_llm
from .task_rule_parser import parse_task_with_rules

#选择 auto/openai/rule、LLM 失败回退、写入 state["task_intent"]
def _failure_intent(state: AgentState, reason: str) -> dict[str, object]:
    return normalize_intent(
        {
            "goal": "water_hazard_screening",
            "intent_type": "inspection",
            "target": "disturbance",
            "attributes": [],
            "relations": [],
            "negatives": [],
            "needs_clarification": True,
            "clarification_question": "当前任务无法被自动解析，请补充目标、空间关系或排除条件。",
            "needs_abstain": False,
            "abstain_reason": reason,
            "priority": "medium",
            "temporal_intent": normalize_temporal_intent(state["task_text"]),
        },
        state,
        parser_source="llm_failed",
    )


async def task_parser_node(state: AgentState) -> AgentState:
    # 任务理解先走 LLM 工具调用；如果失败，再回退到规则解析。
    backend = TASK_PARSER_BACKEND
    if backend not in {"auto", "openai", "rule"}:
        backend = "auto"

    if backend == "rule":
        intent = parse_task_with_rules(state)
    else:
        try:
            intent = await parse_task_with_llm(state)
        except Exception as exc:
            if TASK_PARSER_FALLBACK_TO_RULE:
                append_trace(
                    state,
                    "parse_task.llm_fallback",
                    "LLM task parser failed; rule fallback used",
                    {"error": str(exc)[:300]},
                )
                intent = parse_task_with_rules(state)
            else:
                append_error(state, "parse_task", str(exc))
                intent = _failure_intent(state, str(exc))

    state["task_intent"] = intent
    state["status"] = "INTENT_PARSED"
    append_trace(
        state,
        "parse_task",
        "task intent parsed",
        {"target": intent.get("target"), "parser_source": intent.get("parser_source")},
    )
    return state
