import json

from hydro_remote_agent.tools.predict_cmge_qwen3_vl import _canonicalize_output


def test_predict_boundary_canonicalizes_and_preserves_raw_plan_semantics():
    plan = {
        "schema_version": "cmge.plan.v1",
        "compound_id": "cmge:test",
        "claims": [
            {
                "claim_index": 0,
                "role": "semantic_judgement",
                "route": "direct_answer",
                "intent": "class_presence",
                "request": {
                    "intent": "class_presence",
                    "action": {"type": "direct_answer", "answer": "Yes."},
                },
            },
            {
                "claim_index": 1,
                "role": "dense_localization",
                "route": "tool_call",
                "intent": "shed_segmentation",
                "request": {
                    "intent": "shed_segmentation",
                    "action": {"type": "tool_call", "tool": "multimodal_semantic_segmentation"},
                },
            },
        ],
        "merge": {"type": "claimwise_union", "required_claim_indices": [0, 1]},
    }

    output, provenance = _canonicalize_output(json.dumps(plan))
    normalized = json.loads(output)

    assert normalized["claims"][1]["intent"] == "class_segmentation"
    assert normalized["claims"][1]["request"]["intent"] == "class_segmentation"
    assert normalized["claims"][1]["request"]["action"] == plan["claims"][1]["request"]["action"]
    assert provenance["status"] == "applied"
    assert provenance["changed"]


def test_predict_boundary_keeps_unparseable_output_for_audit():
    output, provenance = _canonicalize_output("not-json")

    assert output == "not-json"
    assert provenance["status"] == "skipped_parse_error"
    assert not provenance["changed"]
    assert provenance["error"]
