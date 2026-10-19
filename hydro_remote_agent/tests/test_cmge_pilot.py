from pathlib import Path

from hydro_remote_agent.tools.build_cmge_pilot import (
    _compound_query,
    build_candidates,
    read_jsonl,
    select_balanced,
)


DATA_PATH = Path(__file__).parents[1] / "data" / "vague_hydro" / "canonical_test.jsonl"


def test_cmge_candidates_use_distinct_source_annotations():
    rows = read_jsonl(DATA_PATH)
    candidates = build_candidates(rows, seed=20260823)

    assert len(candidates) >= 100
    for candidate in candidates[:100]:
        source_ids = {
            str(claim["gold_request"]["request_id"]).rsplit(":", 1)[0]
            for claim in candidate["claims"]
        }
        assert len(source_ids) == 2
        assert candidate["assets"]["image_path"]
        assert candidate["assets"]["point_cloud_path"]


def test_cmge_selection_is_balanced_and_tile_scoped():
    rows = read_jsonl(DATA_PATH)
    selected = select_balanced(build_candidates(rows, seed=20260823), count=100, seed=20260823)

    assert len(selected) == 100
    assert len({str(item["sample_id"]) for item in selected}) >= 50
    assert {str(item["split"]) for item in selected} == {"test"}
    dense_intents = {str(item["claims"][1]["canonical_intent"]) for item in selected}
    assert dense_intents == {
        "class_segmentation",
        "attribute_segmentation",
        "relation_segmentation",
    }


def test_frozen_reference_can_restrict_by_tile():
    from hydro_remote_agent.tools.build_cmge_pilot import build_candidates

    rows = read_jsonl(DATA_PATH)
    candidates = build_candidates(rows, seed=20260823, allowed_sample_ids={"00_000004"})
    assert candidates
    assert {str(item["sample_id"]) for item in candidates} == {"00_000004"}


def test_frozen_reference_tiles_can_be_excluded():
    rows = read_jsonl(DATA_PATH)
    candidates = build_candidates(
        rows,
        seed=20260823,
        excluded_sample_ids={"00_000004"},
    )

    assert candidates
    assert "00_000004" not in {str(item["sample_id"]) for item in candidates}


def test_selection_can_cap_each_tile():
    rows = read_jsonl(DATA_PATH)
    selected = select_balanced(
        build_candidates(rows, seed=20260823),
        count=300,
        seed=20260823,
        max_per_tile=2,
    )
    counts = {}
    for item in selected:
        counts[item["sample_id"]] = counts.get(item["sample_id"], 0) + 1
    assert len(selected) == 300
    assert max(counts.values()) <= 2


def test_compound_query_matches_record_language():
    assert _compound_query("Is Ditch present?", "Segment Ditch.", "en") == (
        "Is Ditch present? Also, Segment Ditch."
    )
    assert _compound_query("是否有沟渠？", "分割沟渠。", "zh") == "是否有沟渠；同时，分割沟渠。"
