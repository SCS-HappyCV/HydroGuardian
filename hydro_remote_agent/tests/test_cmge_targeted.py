from pathlib import Path

from hydro_remote_agent.tools.build_cmge_pilot import build_candidates, read_jsonl
from hydro_remote_agent.tools.build_cmge_targeted import select_targeted, target_matrix


DATA_PATH = Path(__file__).parents[1] / "data" / "vague_hydro" / "canonical_train.jsonl"


def test_target_matrix_preserves_total_and_dense_weights():
    matrix = target_matrix(4000)
    assert sum(matrix.values()) == 4000
    assert sum(value for (_, dense), value in matrix.items() if dense == "class_segmentation") == 800
    assert sum(value for (_, dense), value in matrix.items() if dense == "attribute_segmentation") == 1400
    assert sum(value for (_, dense), value in matrix.items() if dense == "relation_segmentation") == 1800


def test_targeted_selection_is_unique_balanced_and_tile_capped():
    candidates = build_candidates(read_jsonl(DATA_PATH), seed=20260824)
    selected = select_targeted(candidates, count=900, seed=20260824, max_per_tile=4)
    assert len(selected) == 900
    assert len({row["compound_id"] for row in selected}) == 900
    tile_counts = {}
    direct_counts = {}
    dense_counts = {}
    for row in selected:
        tile_counts[row["sample_id"]] = tile_counts.get(row["sample_id"], 0) + 1
        direct = row["claims"][0]["canonical_intent"]
        dense = row["claims"][1]["canonical_intent"]
        direct_counts[direct] = direct_counts.get(direct, 0) + 1
        dense_counts[dense] = dense_counts.get(dense, 0) + 1
    assert max(tile_counts.values()) <= 4
    assert max(direct_counts.values()) - min(direct_counts.values()) <= 1
    assert dense_counts == {
        "class_segmentation": 180,
        "attribute_segmentation": 315,
        "relation_segmentation": 405,
    }
