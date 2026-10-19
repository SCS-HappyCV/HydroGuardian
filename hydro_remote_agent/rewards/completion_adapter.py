"""Strict normalization of TRL completion wrappers to one AgentRequest object."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class CompletionAdapterResult:
    valid: bool
    payload: Optional[dict[str, Any]]
    error: Optional[str]
    raw_json: Optional[str]


def _is_request_object(value: Any) -> bool:
    return isinstance(value, Mapping) and "action" in value and "schema_version" in value


def _parse_json_object(text: str) -> CompletionAdapterResult:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return CompletionAdapterResult(False, None, f"invalid JSON: {exc.msg} at char {exc.pos}", None)
    if not isinstance(value, Mapping):
        return CompletionAdapterResult(False, None, "JSON payload is not an object", text)
    if not _is_request_object(value):
        if "content" in value or "role" in value:
            return CompletionAdapterResult(False, None, "repeated or nested completion wrapper", text)
        return CompletionAdapterResult(False, None, "JSON object is not an AgentRequest payload", text)
    return CompletionAdapterResult(True, dict(value), None, text)


def _from_one_message(message: Mapping[str, Any]) -> CompletionAdapterResult:
    if "content" not in message:
        return CompletionAdapterResult(False, None, "message has no content field", None)
    content = message["content"]
    if isinstance(content, str):
        return _parse_json_object(content)
    if isinstance(content, Mapping) or isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
        return CompletionAdapterResult(False, None, "nested completion wrapper is not accepted", None)
    return CompletionAdapterResult(False, None, "message content is not a JSON string", None)


def adapt_completion(value: Any) -> CompletionAdapterResult:
    """Extract exactly one JSON AgentRequest object without repairing it."""
    if isinstance(value, str):
        return _parse_json_object(value)
    if isinstance(value, Mapping):
        if _is_request_object(value):
            raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            return CompletionAdapterResult(True, dict(value), None, raw)
        if set(value).issubset({"role", "content"}) and "content" in value:
            return _from_one_message(value)
        return CompletionAdapterResult(False, None, "mapping is neither AgentRequest nor one message wrapper", None)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        candidates: list[CompletionAdapterResult] = []
        for index, item in enumerate(value):
            if not isinstance(item, Mapping):
                continue
            if "content" not in item:
                continue
            result = _from_one_message(item)
            if result.valid:
                candidates.append(result)
            elif result.error and "invalid JSON" not in result.error:
                # Non-JSON user/system messages can coexist with one assistant JSON.
                continue
        if not candidates:
            return CompletionAdapterResult(False, None, "no unique JSON AgentRequest object in message list", None)
        payloads = {json.dumps(item.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in candidates}
        if len(payloads) != 1 or len(candidates) != 1:
            return CompletionAdapterResult(False, None, "multiple JSON AgentRequest objects in completion", None)
        only = candidates[0]
        return only
    return CompletionAdapterResult(False, None, f"unsupported completion type: {type(value).__name__}", None)
