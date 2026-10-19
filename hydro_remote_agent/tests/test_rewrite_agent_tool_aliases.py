import json
from pathlib import Path

from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.rewrite_agent_tool_aliases import rewrite_predictions


ROOT = Path(__file__).parents[1].parent
REGISTRY = load_tool_registry(ROOT / "hydro_remote_agent" / "configs" / "tool_registry.yaml")
PREDICTIONS = ROOT / "runs" / "cmge_planner_v1" / "test100_unseen" / "execution_predictions.jsonl"


def test_rewrite_multimodal_to_point_tool_preserves_ids_and_other_requests():
    rows, report = rewrite_predictions(
        PREDICTIONS,
        REGISTRY,
        {"multimodal_semantic_segmentation": "point_semantic_segmentation"},
    )

    assert report["prediction_count"] == 200
    assert report["changed_prediction_count"] == 54
    assert report["transition_counts"] == {
        "multimodal_semantic_segmentation -> point_semantic_segmentation": 54
    }
    assert len({row["id"] for row in rows}) == 200
    for source_line, rewritten in zip(PREDICTIONS.read_text(encoding="utf-8").splitlines(), rows):
        source = json.loads(source_line)
        before = source["prediction"] if isinstance(source["prediction"], dict) else json.loads(source["prediction"])
        after = rewritten["prediction"] if isinstance(rewritten["prediction"], dict) else json.loads(rewritten["prediction"])
        assert before["request_id"] == after["request_id"] == rewritten["id"]
        if not rewritten["tool_alias_rewrite"]["changed"]:
            assert before == after
        else:
            assert "multimodal_semantic_segmentation" in json.dumps(before)
            assert "multimodal_semantic_segmentation" not in rewritten["prediction"]
            assert "point_semantic_segmentation" in rewritten["prediction"]
            assert "image_path" not in rewritten["prediction"]
