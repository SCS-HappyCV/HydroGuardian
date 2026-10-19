from __future__ import annotations

from hydro_remote_agent.legality_diagnostics import (
    classify_strict_error,
    count_values,
    parse_completion_object,
    request_signature,
)
from hydro_remote_agent.tools.analyze_vaguehydro_semantic_diagnostics import analyze


def test_classify_strict_error() -> None:
    assert classify_strict_error(None) == "valid"
    assert classify_strict_error("request_id has an invalid identifier format") == "invalid_identifier"
    assert classify_strict_error("Invalid action.arguments: missing field") == "invalid_tool_arguments"
    assert classify_strict_error("expected_output is incompatible with terminal outputs") == "expected_output_incompatible"
    assert classify_strict_error("JSON object is not an AgentRequest payload") == "missing_required_envelope"


def test_request_signature_for_workflow() -> None:
    signature = request_signature({
        "schema_version": "1.0",
        "action": {
            "type": "workflow",
            "steps": [{"tool": "segment"}, {"tool": "measure"}],
        },
        "expected_output": {"type": "mask", "coordinate_space": "points"},
    })
    assert signature["action_type"] == "workflow"
    assert signature["step_tools"] == ["segment", "measure"]
    assert signature["expected_output_type"] == "mask"


def test_count_values_is_stable() -> None:
    assert count_values([{"kind": "b"}, {"kind": "a"}, {"kind": "b"}], "kind") == {
        "a": 1,
        "b": 2,
    }


def test_parse_completion_object_keeps_partial_agent_envelope() -> None:
    payload = parse_completion_object('{"action":{"type":"workflow"}}')
    assert payload == {"action": {"type": "workflow"}}
    assert parse_completion_object("not json") is None


def test_analysis_recovers_signature_from_rejected_partial_envelope() -> None:
    result = analyze([{
        "id": "case-1",
        "split": "heldout",
        "completion": '{"action":{"type":"workflow","steps":[{"tool":"segment"}]}}',
        "strict_error": "JSON object is not an AgentRequest payload",
        "gold_signature": {
            "action_type": "workflow",
            "tool": None,
            "step_tools": ["segment"],
            "expected_output_type": "point_mask",
            "coordinate_space": "points",
        },
        "decoder_exception": False,
        "eos": True,
        "clipped": False,
        "token_count": 10,
    }])
    row = result["rows"][0]
    assert row["action_type_match"]
    assert row["tool_sequence_match"]
    assert row["error_category"] == "missing_required_envelope"
