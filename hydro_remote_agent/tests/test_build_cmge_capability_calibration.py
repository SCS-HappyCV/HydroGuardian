import pytest

from hydro_remote_agent.tools.build_cmge_capability_calibration import (
    select_calibration_compounds,
)


def _compound(index: int, intent: str, tool: str = "language_guided_point_segmentation"):
    region = f"{index % 3:02d}"
    return {
        "compound_id": f"cmge:{region}_{index:06d}:{intent}",
        "sample_id": f"{region}_{index:06d}",
        "split": "val",
        "claims": [
            {"gold_request": {"action": {"type": "direct_answer"}}},
            {
                "canonical_intent": intent,
                "gold_request": {"action": {"type": "tool_call", "tool": tool}},
            },
        ],
    }


def test_selection_is_balanced_unique_and_deterministic():
    rows = [
        _compound(index * 2 + offset, intent)
        for index in range(30)
        for offset, intent in enumerate(("class_segmentation", "attribute_segmentation"))
    ]
    first = select_calibration_compounds(rows, per_intent=6, seed=17)
    second = select_calibration_compounds(reversed(rows), per_intent=6, seed=17)
    assert [row["compound_id"] for row in first] == [row["compound_id"] for row in second]
    assert len(first) == 12
    assert len({row["sample_id"] for row in first}) == 12
    assert sum(row["claims"][1]["canonical_intent"] == "class_segmentation" for row in first) == 6
    assert sum(row["claims"][1]["canonical_intent"] == "attribute_segmentation" for row in first) == 6


def test_selection_ignores_other_tools():
    rows = [_compound(index, "class_segmentation", "point_semantic_segmentation") for index in range(5)]
    with pytest.raises(ValueError, match="available"):
        select_calibration_compounds(rows, per_intent=1, seed=1)
