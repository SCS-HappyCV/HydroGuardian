from __future__ import annotations

from typing import Any, Dict, List, Mapping

from hydro_remote_agent.backbones.qwen3_vl_planner import planner_messages


DRAFT_INSTRUCTION = (
    " This is round 1 of a two-round ReAct-style planning baseline. Analyze the request, "
    "identify the action type, candidate tools, arguments, dependencies, and uncertainties. "
    "Return a compact JSON planning draft. Do not claim that a specialist tool was executed."
)

FINAL_OBSERVATION = (
    "Observation: no specialist tool has been executed. Re-check the draft against the supplied "
    "ToolSpec, required assets, argument schemas, workflow dependencies, and output contract. "
    "Now return exactly one final AgentRequest JSON object and no reasoning, Markdown, or prose."
)


def react_draft_messages(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    messages = planner_messages(record, prompt_profile="full")
    system_content = messages[0]["content"]
    system_content[0]["text"] += DRAFT_INSTRUCTION
    return messages


def react_final_messages(
    record: Mapping[str, Any],
    draft: str,
) -> List[Dict[str, Any]]:
    messages = react_draft_messages(record)
    messages.extend([
        {"role": "assistant", "content": [{"type": "text", "text": draft.strip()}]},
        {"role": "user", "content": [{"type": "text", "text": FINAL_OBSERVATION}]},
    ])
    return messages
