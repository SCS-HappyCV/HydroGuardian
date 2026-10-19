from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping


CMGE_PLAN_SCHEMA_VERSION = "cmge.plan.v1"
CMGE_SFT_SCHEMA_VERSION = "cmge.sft.v1"
CMGE_CANONICAL_INTENTS = {
    "class_presence",
    "attribute_judgement",
    "relation_judgement",
    "class_segmentation",
    "attribute_segmentation",
    "relation_segmentation",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_intent(claim: Mapping[str, Any]) -> str:
    intent = str(claim.get("intent", ""))
    if intent in CMGE_CANONICAL_INTENTS:
        return intent
    request = claim.get("request")
    action = request.get("action") if isinstance(request, Mapping) else None
    action_type = str(action.get("type", "")) if isinstance(action, Mapping) else ""
    route = str(claim.get("route", ""))
    role = str(claim.get("role", ""))
    if route == "workflow" or action_type == "workflow":
        return "relation_segmentation"
    if route == "direct_answer" or action_type == "direct_answer":
        answer = str(action.get("answer", "")).casefold() if isinstance(action, Mapping) else ""
        if "relation" in answer or " above " in f" {answer} " or " near " in f" {answer} ":
            return "relation_judgement"
        if "attribute" in answer:
            return "attribute_judgement"
        return "class_presence"
    if role == "dense_localization" or route == "tool_call" or action_type == "tool_call":
        return "class_segmentation"
    return intent


def canonicalize_cmge_plan(
    plan: Mapping[str, Any],
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    normalized = json.loads(json.dumps(plan))
    claims = normalized.get("claims")
    if not isinstance(claims, list):
        raise ValueError("CMGE plan claims must be a list")
    changes: List[Dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError("CMGE plan claims must contain objects")
        source = str(claim.get("intent", ""))
        target = _canonical_intent(claim)
        if source == target:
            continue
        claim["intent"] = target
        request = claim.get("request")
        if isinstance(request, dict):
            request["intent"] = target
        changes.append(
            {
                "claim_index": int(claim.get("claim_index", -1)),
                "source_intent": source,
                "target_intent": target,
            }
        )
    return normalized, changes


def _route_for_request(request: Mapping[str, Any]) -> str:
    action = request.get("action")
    action_type = str(action.get("type", "")) if isinstance(action, Mapping) else ""
    if action_type == "direct_answer":
        return "direct_answer"
    if action_type in {"tool_call", "workflow"}:
        return action_type
    return "unsupported"


def build_plan_target(compound: Mapping[str, Any], asset_root: str | None = None) -> Dict[str, Any]:
    from hydro_remote_agent.tools.build_cmge_conditions import _request_for_claim

    claims = compound.get("claims")
    if not isinstance(claims, list) or len(claims) != 2:
        raise ValueError(f"{compound.get('compound_id')} must contain exactly two claims")
    plan_claims = []
    for index, claim in enumerate(claims):
        request = _request_for_claim(compound, index, asset_root)
        plan_claims.append(
            {
                "claim_id": f"{compound['compound_id']}:claim{index}",
                "claim_index": index,
                "role": str(claim.get("role", "")),
                "intent": str(claim.get("canonical_intent", "")),
                "route": _route_for_request(request),
                "request": request,
            }
        )
    return {
        "schema_version": CMGE_PLAN_SCHEMA_VERSION,
        "compound_id": str(compound["compound_id"]),
        "claims": plan_claims,
        "merge": {
            "type": "claimwise_union",
            "required_claim_indices": [0, 1],
        },
    }


def _system_prompt(record: Mapping[str, Any]) -> str:
    tools = record.get("tools", [])
    return (
        "You are the CMGE claim-wise planner for hydrological point-cloud tasks. "
        "Decompose the compound request into exactly two independent semantic claims. "
        "For each claim, choose direct_answer for a text judgement, tool_call for a "
        "single expert request, or workflow for a dependency-composed expert request. "
        "Return exactly one JSON object and no prose. Preserve compound_id exactly. "
        "The output must contain schema_version cmge.plan.v1, two claims with claim_index "
        "0 and 1, route, and a valid component AgentRequest in request. Include merge "
        "with type claimwise_union and required_claim_indices [0,1]. Use only registered "
        "tools and preserve asset paths from the user payload. Available tools: "
        + canonical_json(tools)
    )


def cmge_planner_messages(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    compound_id = str(record.get("id") or record.get("compound_id") or "")
    if not compound_id:
        raise ValueError("CMGE record is missing compound_id")
    messages = record.get("messages")
    if not isinstance(messages, list):
        raise ValueError("CMGE record messages must be a list")
    user_message = next(
        (
            message
            for message in messages
            if isinstance(message, Mapping) and message.get("role") == "user"
        ),
        None,
    )
    if user_message is None:
        raise ValueError(f"CMGE record {compound_id!r} has no user message")
    user_payload = json.loads(str(user_message.get("content", "")))
    if not isinstance(user_payload, dict):
        raise ValueError("CMGE user content must be a JSON object")
    user_payload["compound_id"] = compound_id
    images = record.get("images")
    if not isinstance(images, list) or not images:
        raise ValueError(f"CMGE record {compound_id!r} has no image")
    return [
        {
            "role": "system",
            "content": [{"type": "text", "text": _system_prompt(record)}],
        },
        {
            "role": "user",
            "content": [
                *[{"type": "image", "image": str(path)} for path in images],
                {"type": "text", "text": canonical_json(user_payload)},
            ],
        },
    ]


def cmge_training_messages(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    messages = cmge_planner_messages(record)
    target = cmge_assistant_target(record)
    messages.append(
        {
            "role": "assistant",
            "content": [{"type": "text", "text": canonical_json(target)}],
        }
    )
    return messages


def cmge_assistant_target(record: Mapping[str, Any]) -> Dict[str, Any]:
    messages = record.get("messages")
    if not isinstance(messages, list):
        raise ValueError("CMGE record messages must be a list")
    for message in reversed(messages):
        if isinstance(message, Mapping) and message.get("role") == "assistant":
            payload = json.loads(str(message.get("content", "")))
            if not isinstance(payload, dict):
                break
            return payload
    raise ValueError(f"CMGE record {record.get('id')!r} has no JSON assistant target")
