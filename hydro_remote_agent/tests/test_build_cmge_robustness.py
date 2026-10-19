import json
from pathlib import Path

from hydro_remote_agent.cmge_planner import cmge_assistant_target
from hydro_remote_agent.tools.build_cmge_robustness import build_robustness_records


ROOT = Path(__file__).parents[1].parent
SFT = ROOT / "runs" / "cmge_planner_v1" / "test100_unseen" / "cmge_sft.jsonl"
MANIFEST = ROOT / "runs" / "cmge_planner_v1" / "test100_unseen" / "conditions" / "compound_manifest.jsonl"


def test_build_robustness_records_preserves_gold_semantics_and_rewrites_ids():
    rows, report = build_robustness_records(SFT, MANIFEST)

    assert report["record_count"] == 300
    assert report["variant_counts"] == {
        "first_then": 100,
        "numbered": 100,
        "same_scene": 100,
    }
    assert len({row["id"] for row in rows}) == 300
    for row in rows[:6]:
        user = json.loads(row["messages"][1]["content"])
        target = cmge_assistant_target(row)
        assert user["query"]
        assert user["compound_id"] == row["id"]
        assert target["compound_id"] == row["id"]
        assert [claim["claim_index"] for claim in target["claims"]] == [0, 1]
        assert all(claim["claim_id"].startswith(row["id"]) for claim in target["claims"])
