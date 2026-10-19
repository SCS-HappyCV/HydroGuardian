from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Mapping, Sequence, Tuple


PLANNER_PROMPT_PROFILES = (
    "full",
    "minimal_toolspec",
    "no_tool_descriptions",
    "no_request_examples",
    "no_workflow_example",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} must contain an object")
            records.append(payload)
    return records


def assistant_target(record: Mapping[str, Any]) -> Dict[str, Any]:
    messages = record.get("messages")
    if not isinstance(messages, list):
        raise ValueError("record messages must be a list")
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "assistant":
            payload = json.loads(str(message.get("content", "")))
            if not isinstance(payload, dict):
                break
            return payload
    raise ValueError(f"record {record.get('id')!r} has no JSON assistant target")


def action_type(record: Mapping[str, Any]) -> str:
    action = assistant_target(record).get("action")
    return str(action.get("type", "")) if isinstance(action, dict) else ""


def _stable_rank(record: Mapping[str, Any], seed: int) -> str:
    key = f"{seed}:{record.get('id', '')}".encode("utf-8")
    return hashlib.sha256(key).hexdigest()


def stratified_sample(
    records: Sequence[Mapping[str, Any]],
    count: int,
    seed: int,
) -> List[Dict[str, Any]]:
    if count <= 0:
        return []
    buckets: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for raw_record in records:
        record = dict(raw_record)
        key = (
            str(record.get("language", "unknown")),
            str(record.get("ambiguity_level", "unknown")),
            action_type(record) or "unknown",
        )
        buckets[key].append(record)
    queues: Dict[Tuple[str, str, str], Deque[Dict[str, Any]]] = {}
    for key, values in buckets.items():
        values.sort(key=lambda item: _stable_rank(item, seed))
        queues[key] = deque(values)

    selected: List[Dict[str, Any]] = []
    ordered_keys = sorted(queues)
    while len(selected) < count and ordered_keys:
        next_keys: List[Tuple[str, str, str]] = []
        for key in ordered_keys:
            queue = queues[key]
            if queue and len(selected) < count:
                selected.append(queue.popleft())
            if queue:
                next_keys.append(key)
        ordered_keys = next_keys
    return selected


ACTION_SHAPES = {
    "direct_answer": {
        "type": "direct_answer",
        "answer": "answer grounded in the supplied image/assets",
    },
    "tool_call": {
        "type": "tool_call",
        "tool": "registered_tool_name",
        "arguments": {},
        "verification": "auto|required|skip",
    },
    "workflow": {
        "type": "workflow",
        "steps": [
            {
                "step_id": "step_name",
                "tool": "registered_tool_name",
                "arguments": {},
                "depends_on": [],
                "verification": "auto|required|skip",
            }
        ],
    },
    "clarification": {
        "type": "clarification",
        "question": "question for the missing information",
        "missing_fields": ["field_name"],
    },
    "abstain": {
        "type": "abstain",
        "reason": "why the request is unsupported",
        "error_code": "unsupported_capability",
        "recoverable": False,
    },
}

VALID_REQUEST_EXAMPLES = [
    {
        "schema_version": "1.0",
        "request_id": "example:direct",
        "intent": "class_presence",
        "action": {"type": "direct_answer", "answer": "The target is visible."},
        "expected_output": {"type": "text", "coordinate_space": "none"},
    },
    {
        "schema_version": "1.0",
        "request_id": "example:tool",
        "intent": "class_segmentation",
        "action": {
            "type": "tool_call",
            "tool": "language_guided_point_segmentation",
            "arguments": {
                "image_path": "tile.png",
                "point_cloud_path": "tile.txt",
                "query": "Segment the waterline.",
                "target_class_ids": [13],
                "return_probabilities": True,
            },
            "verification": "required",
        },
        "expected_output": {
            "type": "point_mask",
            "coordinate_space": "source_point_cloud",
        },
    },
    {
        "schema_version": "1.0",
        "request_id": "example:workflow",
        "intent": "relation_segmentation",
        "action": {
            "type": "workflow",
            "steps": [
                {
                    "step_id": "segment",
                    "tool": "multimodal_semantic_segmentation",
                    "arguments": {
                        "image_path": "tile.png",
                        "point_cloud_path": "tile.txt",
                        "target_class_ids": [4, 13],
                    },
                },
                {
                    "step_id": "relation",
                    "tool": "geometry_relation_analysis",
                    "depends_on": ["segment"],
                    "arguments": {
                        "point_cloud_path": "tile.txt",
                        "segmentation_result_path": "${segment.artifacts.point_labels}",
                        "operation": "near",
                        "target_class_id": 4,
                        "reference_class_id": 13,
                        "distance_threshold_m": 3.0,
                    },
                },
            ],
        },
        "expected_output": {
            "type": "point_mask",
            "coordinate_space": "source_point_cloud",
        },
    },
]


def _without_descriptions(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_descriptions(child)
            for key, child in value.items()
            if key != "description"
        }
    if isinstance(value, list):
        return [_without_descriptions(child) for child in value]
    return value


def planner_system_prompt(
    record: Mapping[str, Any],
    prompt_profile: str = "full",
) -> str:
    if prompt_profile not in PLANNER_PROMPT_PROFILES:
        raise ValueError(f"Unsupported Planner prompt profile {prompt_profile!r}")
    messages = record.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("record messages must be a non-empty list")
    base = next(
        (
            str(message.get("content", ""))
            for message in messages
            if isinstance(message, dict) and message.get("role") == "system"
        ),
        "",
    )
    tools = record.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("record tools must be a non-empty list")
    available_tools = (
        _without_descriptions(tools)
        if prompt_profile in {"minimal_toolspec", "no_tool_descriptions"}
        else tools
    )
    examples = VALID_REQUEST_EXAMPLES
    if prompt_profile in {"minimal_toolspec", "no_request_examples"}:
        examples = []
    elif prompt_profile == "no_workflow_example":
        examples = [
            example
            for example in VALID_REQUEST_EXAMPLES
            if example["action"]["type"] != "workflow"
        ]
    example_text = (
        " Valid complete AgentRequest examples (copy their structure, not their values): "
        + canonical_json(examples)
        if examples
        else ""
    )
    return (
        base
        + " Do not emit native function-call tags. Return one JSON object beginning with { and "
        "ending with }. Never write a json label before it. The action field MUST be an object, "
        "never a string. The expected_output field MUST be an object with type and "
        "coordinate_space, never a string or file path. Copy request_id exactly from the user "
        "payload. Choose intent from class_presence, class_segmentation, attribute_judgement, "
        "attribute_segmentation, relation_judgement, relation_segmentation, or "
        "full_scene_segmentation. For direct answers, inspect the supplied image and do not "
        "invent objects that are not visible. Action shapes: "
        + canonical_json(ACTION_SHAPES)
        + example_text
        + " Available tools: "
        + canonical_json(available_tools)
    )


def planner_messages(
    record: Mapping[str, Any],
    prompt_profile: str = "full",
) -> List[Dict[str, Any]]:
    record_id = str(record.get("id", ""))
    if not record_id:
        raise ValueError("record is missing id")
    messages = record.get("messages")
    if not isinstance(messages, list):
        raise ValueError("record messages must be a list")
    user_message = next(
        (
            message
            for message in messages
            if isinstance(message, dict) and message.get("role") == "user"
        ),
        None,
    )
    if user_message is None:
        raise ValueError(f"record {record_id!r} has no user message")
    user_payload = json.loads(str(user_message.get("content", "")))
    if not isinstance(user_payload, dict):
        raise ValueError("user content must be a JSON object")
    user_payload["request_id"] = record_id

    images = record.get("images")
    if not isinstance(images, list) or not images:
        raise ValueError(f"record {record_id!r} has no image")
    image_blocks = [
        {"type": "image", "image": str(image_path)} for image_path in images
    ]
    return [
        {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": planner_system_prompt(record, prompt_profile=prompt_profile),
                },
            ],
        },
        {
            "role": "user",
            "content": [
                *image_blocks,
                {"type": "text", "text": canonical_json(user_payload)},
            ],
        },
    ]


def planner_training_messages(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    messages = planner_messages(record)
    target = assistant_target(record)
    messages.append(
        {
            "role": "assistant",
            "content": [{"type": "text", "text": canonical_json(target)}],
        }
    )
    return messages


def iter_batches(values: Sequence[Any], batch_size: int) -> Iterable[Sequence[Any]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    for start in range(0, len(values), batch_size):
        yield values[start : start + batch_size]
