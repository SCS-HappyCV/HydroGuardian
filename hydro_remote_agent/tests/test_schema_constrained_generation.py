from __future__ import annotations

import json

from hydro_remote_agent.schema_constrained_generation import (
    AgentRequestPrefixParser,
    is_non_progress_json_whitespace,
)


TOOLS = {"multimodal_semantic_segmentation", "language_guided_point_segmentation"}
ARGUMENTS = {
    "image_path": {"type": "string"},
    "point_cloud_path": {"type": "string"},
    "target_class_ids": {"type": "array", "items": {"type": "integer"}},
    "return_probabilities": {"type": "boolean"},
    "query": {"type": "string"},
}


def parser() -> AgentRequestPrefixParser:
    def validate(value):
        return (
            value.get("schema_version") == "1.0"
            and isinstance(value.get("request_id"), str)
            and value.get("intent") == "attribute_segmentation"
            and isinstance(value.get("action"), dict)
            and value["action"].get("type") == "tool_call"
        )

    return AgentRequestPrefixParser(
        TOOLS,
        ARGUMENTS,
        {"point_mask"},
        {"source_point_cloud"},
        validate,
    )


def valid_request() -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "q:test:中文",
        "intent": "attribute_segmentation",
        "action": {
            "type": "tool_call",
            "tool": "language_guided_point_segmentation",
            "arguments": {
                "image_path": "含有中文/引号\\\"/换行\\n.png",
                "point_cloud_path": "cloud.txt",
                "target_class_ids": [8, 9],
                "return_probabilities": True,
                "query": "耕地，连续分布",
            },
            "verification": "required",
        },
        "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
    }


def test_chinese_escapes_nested_objects_and_arrays() -> None:
    text = json.dumps(valid_request(), ensure_ascii=False, separators=(",", ":"))
    state = parser()
    for chunk in (text[:17], text[17:91], text[91:]):
        assert state.feed(chunk), state.error
    assert state.result().complete


def test_unterminated_string_is_valid_prefix_but_not_complete() -> None:
    state = parser()
    assert state.feed('{"request_id":"中文')
    assert state.result().valid and not state.result().complete
    assert state.result().mode == "string"


def test_illegal_field_is_rejected_online() -> None:
    state = parser()
    assert not state.feed('{"forbidden"')
    assert "allowed field" in (state.error or "")


def test_illegal_enum_is_rejected_online() -> None:
    state = parser()
    assert not state.feed('{"intent":"not_an_intent')
    assert "allowed enum" in (state.error or "")


def test_escaped_schema_field_name_is_rejected_before_unicode_dead_end() -> None:
    state = parser()
    assert not state.feed('{"schema_version":"1.0","\\')
    assert "schema field names" in (state.error or "")


def test_escaped_enum_value_is_rejected_before_unicode_dead_end() -> None:
    state = parser()
    assert not state.feed('{"intent":"attribute_segmentation\\')
    assert "schema enum values" in (state.error or "")


def test_unicode_escapes_remain_valid_in_free_text_values() -> None:
    text = json.dumps(valid_request(), ensure_ascii=True, separators=(",", ":"))
    state = parser()
    assert state.feed(text), state.error
    assert state.result().complete


def test_comma_is_rejected_when_object_has_no_unused_schema_fields() -> None:
    state = parser()
    assert not state.feed(
        '{"expected_output":{"type":"point_mask",'
        '"coordinate_space":"source_point_cloud",'
    )
    assert "no unused fields" in (state.error or "")


def test_eos_condition_only_after_complete_valid_request() -> None:
    text = json.dumps(valid_request(), ensure_ascii=False, separators=(",", ":"))
    state = parser()
    assert state.feed(text[:-1]) and not state.result().complete
    assert state.feed(text[-1:]) and state.result().complete
    clone = state.clone()
    assert not clone.feed("x")


def test_invalid_complete_agent_request_cannot_close() -> None:
    value = valid_request()
    value["schema_version"] = "2.0"
    state = parser()
    assert not state.feed(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def test_syntax_only_parser_can_close_before_separate_semantic_scoring() -> None:
    value = valid_request()
    value["action"] = {"type": "tool_call"}
    state = AgentRequestPrefixParser(
        TOOLS,
        ARGUMENTS,
        {"point_mask"},
        {"source_point_cloud"},
        complete_validator=None,
    )
    assert state.feed(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    assert state.result().complete


def test_root_cannot_close_before_required_envelope_is_complete() -> None:
    state = AgentRequestPrefixParser(
        TOOLS,
        ARGUMENTS,
        {"point_mask"},
        {"source_point_cloud"},
        complete_validator=None,
    )
    assert state.feed('{"action":{"type":"tool_call"}')
    trial = state.clone()
    assert not trial.feed("}")
    assert "missing required fields" in (trial.error or "")
    assert "schema_version" in (trial.error or "")


def test_expected_output_remains_optional_for_root_closure() -> None:
    value = valid_request()
    value.pop("expected_output")
    state = parser()
    assert state.feed(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    assert state.result().complete


def test_workflow_step_requires_step_id_tool_and_arguments_before_close() -> None:
    value = valid_request()
    value["action"] = {
        "type": "workflow",
        "steps": [{"tool": "language_guided_point_segmentation", "arguments": {}}],
    }
    state = AgentRequestPrefixParser(
        TOOLS, ARGUMENTS, {"point_mask"}, {"source_point_cloud"}, complete_validator=None
    )
    assert state.feed(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) is False
    assert "missing required fields" in (state.error or "")
    assert "step_id" in (state.error or "")


def test_workflow_step_id_prefix_and_length_are_constrained() -> None:
    state = parser()
    assert not state.feed('{"schema_version":"1.0","request_id":"q:x","intent":"attribute_segmentation","action":{"type":"workflow","steps":[{"step_id":"1')
    assert "identifier prefix" in (state.error or "")
    state = parser()
    long_id = "a" * 49
    assert not state.feed(
        '{"schema_version":"1.0","request_id":"q:x","intent":"attribute_segmentation",'
        '"action":{"type":"workflow","steps":[{"step_id":"' + long_id
    )
    assert "identifier prefix" in (state.error or "")


def test_candidate_list_is_not_filtered_when_scored() -> None:
    candidates = [json.dumps(valid_request(), ensure_ascii=False), '{"intent":"bad"']
    rewards = []
    for value in candidates:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            rewards.append(0.0)
        else:
            rewards.append(1.0 if parsed.get("intent") == "attribute_segmentation" else 0.0)
    retained = list(zip(candidates, rewards))
    assert len(retained) == len(candidates)
    assert retained[1][1] == 0.0


def test_structure_whitespace_is_non_progress() -> None:
    state = parser()
    text = '{"schema_version":"1.0"'
    assert state.feed(text)
    assert is_non_progress_json_whitespace(state.result(), text, text + " \n\t")


def test_structure_token_with_closer_is_progress() -> None:
    state = parser()
    text = '{"schema_version":"1.0"'
    assert state.feed(text)
    assert not is_non_progress_json_whitespace(state.result(), text, text + " }")


def test_whitespace_inside_free_text_string_is_progress() -> None:
    state = parser()
    text = '{"request_id":"hello'
    assert state.feed(text)
    assert state.result().mode == "string"
    assert not is_non_progress_json_whitespace(state.result(), text, text + " ")
