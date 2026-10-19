from __future__ import annotations

from collections import Counter
import json
from typing import Any, Mapping, Optional, Sequence


def classify_strict_error(error: Optional[str]) -> str:
    if error is None:
        return "valid"
    lowered = error.lower()
    rules = (
        ("invalid_json", ("invalid json", "json payload")),
        ("completion_wrapper", ("completion wrapper", "message content")),
        ("missing_required_envelope", ("not an agentrequest payload",)),
        ("invalid_identifier", ("invalid identifier format",)),
        ("unknown_tool", ("unknown tool",)),
        ("invalid_tool_arguments", ("invalid action.arguments", "invalid action.steps")),
        ("verifier_unavailable", ("no registered verifier",)),
        ("workflow_dependency", ("depends_on", "non-previous step", "duplicate step ids")),
        ("expected_output_incompatible", ("expected_output is incompatible", "does not directly produce text", "can only satisfy expected_output")),
        ("missing_or_wrong_type", ("must be a non-empty string", "must be an object", "must be a list", "must be a boolean")),
    )
    for category, needles in rules:
        if any(needle in lowered for needle in needles):
            return category
    return "other_semantic"


def parse_completion_object(completion: str) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(completion)
    except (TypeError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def request_signature(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {
            "action_type": None,
            "tool": None,
            "step_tools": [],
            "expected_output_type": None,
            "coordinate_space": None,
            "top_level_keys": [],
            "action_keys": [],
        }
    action = payload.get("action")
    action = action if isinstance(action, Mapping) else {}
    steps = action.get("steps")
    step_tools = []
    if isinstance(steps, Sequence) and not isinstance(steps, (str, bytes)):
        step_tools = [
            step.get("tool")
            for step in steps
            if isinstance(step, Mapping) and isinstance(step.get("tool"), str)
        ]
    expected = payload.get("expected_output")
    expected = expected if isinstance(expected, Mapping) else {}
    return {
        "action_type": action.get("type"),
        "tool": action.get("tool"),
        "step_tools": step_tools,
        "expected_output_type": expected.get("type"),
        "coordinate_space": expected.get("coordinate_space"),
        "top_level_keys": sorted(str(key) for key in payload),
        "action_keys": sorted(str(key) for key in action),
    }


def count_values(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(str(row.get(key)) for row in rows)
    return dict(sorted(counts.items()))
