from __future__ import annotations

from hydro_remote_agent.generation_termination import complete_json_prefix_end


def test_complete_json_prefix_handles_nested_objects_and_strings() -> None:
    text = '  {"action":{"arguments":{"text":"brace } and \\\"quote\\\""}}} trailing'
    end = complete_json_prefix_end(text)
    assert end is not None
    assert text[:end].strip().endswith("}}}")
    assert text[end:] == " trailing"


def test_complete_json_prefix_rejects_incomplete_object() -> None:
    assert complete_json_prefix_end('{"action":{"type":"tool_call"}') is None


def test_complete_json_prefix_ignores_leading_fence_text() -> None:
    text = '```json\n{"action":{"type":"direct_answer"}}\n```'
    end = complete_json_prefix_end(text)
    assert end is not None
    assert text[end:].startswith("\n```")
