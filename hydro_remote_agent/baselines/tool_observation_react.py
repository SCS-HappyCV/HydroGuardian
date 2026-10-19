from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping

from hydro_remote_agent.backbones.qwen3_vl_planner import planner_messages


REACT_SYSTEM_SUFFIX = (
    " This is a tool-observation ReAct baseline. First return one complete AgentRequest JSON. "
    "The runtime will execute it and return a bounded observation. After the observation, either "
    "repair the request or keep it unchanged. Never invent artifacts or claim success beyond the observation."
)

FINAL_INSTRUCTION = (
    "Use the real runtime observation below to produce the final AgentRequest. Return exactly one "
    "AgentRequest JSON object and no reasoning, Markdown, status wrapper, or prose. Preserve request_id.\n"
)


def initial_messages(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    messages = planner_messages(record, prompt_profile="full")
    messages[0]["content"][0]["text"] += REACT_SYSTEM_SUFFIX
    return messages


def compact_execution_observation(execution: Mapping[str, Any]) -> Dict[str, Any]:
    result = execution.get("result")
    observation: Dict[str, Any] = {
        "status": execution.get("status", "unknown"),
        "error": execution.get("error"),
    }
    if not isinstance(result, Mapping):
        return observation
    observation.update({
        "execution_mode": result.get("execution_mode"),
        "outcome": result.get("outcome"),
        "required_tools": result.get("required_tools", []),
        "response": result.get("response"),
        "terminal_artifacts": result.get("terminal_artifacts", {}),
        "warnings": result.get("warnings", []),
    })
    workflow = result.get("workflow_result")
    if isinstance(workflow, Mapping):
        observation["steps"] = [
            {
                "step_id": step.get("step_id"),
                "tool": step.get("tool"),
                "status": step.get("status"),
                "metrics": (
                    step.get("result", {}).get("metrics", {})
                    if isinstance(step.get("result"), Mapping)
                    else {}
                ),
                "artifacts": (
                    step.get("result", {}).get("artifacts", {})
                    if isinstance(step.get("result"), Mapping)
                    else {}
                ),
                "verification": (
                    step.get("verification_result", {}).get("metrics", {})
                    if isinstance(step.get("verification_result"), Mapping)
                    else None
                ),
            }
            for step in workflow.get("steps", [])
            if isinstance(step, Mapping)
        ]
    return observation


def final_messages(
    record: Mapping[str, Any],
    initial_prediction: str,
    observation: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    messages = initial_messages(record)
    messages.extend([
        {"role": "assistant", "content": [{"type": "text", "text": initial_prediction.strip()}]},
        {
            "role": "user",
            "content": [{
                "type": "text",
                "text": FINAL_INSTRUCTION + json.dumps(observation, ensure_ascii=False, sort_keys=True),
            }],
        },
    ])
    return messages
