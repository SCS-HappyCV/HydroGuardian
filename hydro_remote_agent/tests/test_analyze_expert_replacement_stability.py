import json
from pathlib import Path

import pytest

from hydro_remote_agent.tools.analyze_expert_replacement_stability import analyze, write_markdown


def _write_rows(root: Path, condition: str, scores: list[float]) -> None:
    path = root / condition / "task_quality_rows.jsonl"
    path.parent.mkdir(parents=True)
    with path.open("w", encoding="utf-8") as handle:
        for index, score in enumerate(scores):
            row = {
                "id": f"q{index}",
                "task_score": score,
                "routing_exact": True,
                "execution_succeeded": True,
                "gold_action_type": "tool_call",
                "task_type": "class",
            }
            handle.write(json.dumps(row) + "\n")


def test_analyze_reports_rank_reversal_and_failure_transitions(tmp_path: Path) -> None:
    before, after = tmp_path / "before", tmp_path / "after"
    _write_rows(before, "agent_a", [0.8, 0.8])
    _write_rows(before, "agent_b", [0.4, 0.4])
    _write_rows(after, "agent_a", [0.1, 0.1])
    _write_rows(after, "agent_b", [0.7, 0.7])

    report, transitions = analyze(before, after, ["agent_a", "agent_b"], expected_count=2)

    assert report["ranking_stability"]["before_ranking"] == ["agent_a", "agent_b"]
    assert report["ranking_stability"]["after_ranking"] == ["agent_b", "agent_a"]
    assert report["ranking_stability"]["spearman"] == pytest.approx(-1.0)
    assert report["conditions"]["agent_a"]["failure_transitions"]["execution_success_low_outcome"]["introduced"] == 2
    assert len(transitions) == 4


def test_analyze_rejects_mismatched_request_population(tmp_path: Path) -> None:
    before, after = tmp_path / "before", tmp_path / "after"
    _write_rows(before, "agent", [0.1, 0.2])
    _write_rows(after, "agent", [0.1])

    with pytest.raises(ValueError, match="expected 2 unique rows"):
        analyze(before, after, ["agent"], expected_count=2)


def test_custom_labels_and_integrity_are_written_to_markdown(tmp_path: Path) -> None:
    before, after = tmp_path / "before", tmp_path / "after"
    _write_rows(before, "agent", [0.4, 0.6])
    _write_rows(after, "agent", [0.3, 0.5])

    report, _ = analyze(
        before,
        after,
        ["agent"],
        expected_count=2,
        before_label="PTv3",
        after_label="GUFNet",
        before_integrity="zero_overlap_ptv3",
        after_integrity="zero_overlap_gufnet",
    )
    markdown = tmp_path / "stability.md"
    write_markdown(report, markdown)

    text = markdown.read_text(encoding="utf-8")
    assert "PTv3-to-GUFNet" in text
    assert "| Condition | PTv3 outcome | GUFNet outcome |" in text
    assert report["before_integrity"] == "zero_overlap_ptv3"
    assert report["after_integrity"] == "zero_overlap_gufnet"
