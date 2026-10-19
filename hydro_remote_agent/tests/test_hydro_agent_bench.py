import json
from pathlib import Path

import pytest

from hydro_remote_agent.tools.analyze_hydro_agent_bench import (
    analyze,
    no_target_metrics,
    stratified_bootstrap_ci,
    write_markdown,
)


def test_stratified_bootstrap_preserves_estimate() -> None:
    rows = [
        {"gold_action_type": "tool_call", "value": 0.0},
        {"gold_action_type": "tool_call", "value": 1.0},
        {"gold_action_type": "workflow", "value": 0.5},
        {"gold_action_type": "workflow", "value": 0.5},
    ]
    result = stratified_bootstrap_ci(rows, lambda row: row["value"], 200, 0.95, 7)
    assert result["estimate"] == pytest.approx(0.5)
    assert result["lower"] <= result["estimate"] <= result["upper"]


def test_no_target_metrics() -> None:
    rows = [
        {"score_kind": "binary_mask", "metrics": {"is_no_target": True, "predicted_no_target": True}},
        {"score_kind": "binary_mask", "metrics": {"is_no_target": True, "predicted_no_target": False}},
        {"score_kind": "binary_mask", "metrics": {"is_no_target": False, "predicted_no_target": True}},
    ]
    result = no_target_metrics(rows)
    assert result["precision"] == pytest.approx(0.5)
    assert result["recall"] == pytest.approx(0.5)
    assert result["f1"] == pytest.approx(0.5)


def test_analyze_rejects_population_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "rows"
    for condition, request_id in [("a", "q1"), ("b", "q2")]:
        path = root / condition / "task_quality_rows.jsonl"
        path.parent.mkdir(parents=True)
        row = {
            "id": request_id,
            "gold_action_type": "tool_call",
            "routing_exact": True,
            "execution_succeeded": True,
            "task_score": 0.5,
            "score_kind": "binary_mask",
            "metrics": {"is_no_target": False, "predicted_no_target": False},
        }
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    config = {
        "protocol_id": "test",
        "seed": 1,
        "population": {"request_count": 1},
        "task_rows_root": "rows",
        "conditions": ["a", "b"],
        "learned_conditions": ["a", "b"],
        "statistics": {
            "bootstrap_samples": 10,
            "confidence_level": 0.95,
            "low_outcome_threshold": 0.25,
            "high_outcome_threshold": 0.5,
        },
        "independent_expert_replacement": {},
        "scope": {"excluded": []},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="population differs"):
        analyze(config_path, tmp_path)


@pytest.mark.parametrize(
    ("eligible", "expected"),
    [(True, "formal-outcome eligible"), (False, "pilot evidence only")],
)
def test_markdown_integrity_note_tracks_protocol(
    tmp_path: Path, eligible: bool, expected: str
) -> None:
    report = {
        "protocol_id": "test",
        "status": "formal_complete" if eligible else "pilot_complete",
        "conditions": {},
        "agent_level_rank_agreement": {
            "routing_vs_outcome_spearman": None,
            "execution_vs_outcome_spearman": None,
        },
        "limitations": [],
        "data_integrity": {"formal_outcome_eligible": eligible},
    }
    path = tmp_path / "report.md"
    write_markdown(report, path)
    assert expected in path.read_text(encoding="utf-8")
