from __future__ import annotations

import copy
from typing import Any, Dict, Mapping, Sequence


def parse_tool_aliases(values: Sequence[str], registry) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for value in values:
        source, separator, target = value.partition("=")
        source, target = source.strip(), target.strip()
        if not separator or not source or not target:
            raise ValueError(f"Invalid tool alias {value!r}; expected SOURCE=TARGET")
        if source in aliases:
            raise ValueError(f"Duplicate tool alias source {source!r}")
        registry.get(target)
        aliases[source] = target
    return aliases


def execution_request_with_aliases(
    request: Mapping[str, Any],
    tool_aliases: Mapping[str, str],
    registry,
) -> Dict[str, Any]:
    payload = copy.deepcopy(dict(request))
    action = payload.get("action")
    if not isinstance(action, dict):
        return payload
    calls = [action] if action.get("type") == "tool_call" else action.get("steps", [])
    if not isinstance(calls, list):
        return payload
    for call in calls:
        if not isinstance(call, dict) or call.get("tool") not in tool_aliases:
            continue
        call["tool"] = tool_aliases[str(call["tool"])]
        tool = registry.get(str(call["tool"]))
        properties = tool.arguments_schema.get("properties", {})
        arguments = call.get("arguments")
        if isinstance(arguments, dict) and isinstance(properties, dict):
            call["arguments"] = {
                name: value for name, value in arguments.items() if name in properties
            }
    return payload
