import json
from pathlib import Path

import pytest

from hydro_remote_agent.tools.expand_cmge_predictions import expand_predictions


ROOT = Path(__file__).parents[1]
REGISTRY = ROOT / "configs" / "tool_registry.yaml"
PREDICTIONS = (
    ROOT.parent
    / "runs"
    / "cmge_planner_v1"
    / "test100_unseen"
    / "gate500_predictions.jsonl"
)


def test_expand_cmge_predictions_produces_two_valid_requests_per_plan():
    rows, report = expand_predictions(PREDICTIONS, REGISTRY)

    assert report["compound_count"] == 100
    assert report["claim_count"] == 200
    assert report["route_counts"] == {
        "direct_answer": 100,
        "tool_call": 68,
        "workflow": 32,
    }
    assert len({row["id"] for row in rows}) == 200
    assert all(row["prediction"]["request_id"] == row["id"] for row in rows)


def test_expand_cmge_predictions_rejects_wrong_compound_id(tmp_path: Path):
    row = json.loads(PREDICTIONS.read_text(encoding="utf-8").splitlines()[0])
    plan = json.loads(row["prediction"])
    plan["compound_id"] = "wrong"
    row["prediction"] = json.dumps(plan)
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="compound_id"):
        expand_predictions(path, REGISTRY)
