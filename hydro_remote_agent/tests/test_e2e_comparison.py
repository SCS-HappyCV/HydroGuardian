from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from hydro_remote_agent.evaluation.e2e_comparison import (
    compare_e2e_conditions,
    freeze_stratified_subset,
    summarize_e2e_condition,
)


def _request(request_id: str, action_type: str) -> dict:
    if action_type == "direct_answer":
        action = {"type": action_type, "answer": "yes"}
    elif action_type == "tool_call":
        action = {
            "type": action_type,
            "tool": "point_semantic_segmentation",
            "arguments": {"point_cloud_path": "/data/a.txt"},
        }
    else:
        action = {"type": action_type, "steps": []}
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "intent": "test",
        "action": action,
        "expected_output": {"type": "text", "coordinate_space": "none"},
    }


def _records() -> list[dict]:
    records = []
    for action in ("direct_answer", "tool_call", "workflow"):
        for language in ("en", "zh"):
            for level in ("L0", "L1", "L2", "L3"):
                for index in range(4):
                    request_id = f"{action}:{language}:{level}:{index}"
                    records.append({
                        "id": request_id,
                        "sample_id": request_id,
                        "language": language,
                        "ambiguity_level": level,
                        "gold_request": _request(request_id, action),
                    })
    return records


def test_freeze_stratified_subset_is_balanced_and_deterministic() -> None:
    first, report = freeze_stratified_subset(_records(), seed=7)
    second, _ = freeze_stratified_subset(_records(), seed=7)
    assert [row["id"] for row in first] == [row["id"] for row in second]
    assert len(first) == 50
    assert len({row["sample_id"] for row in first}) == 50
    assert report["observed_action_counts"] == {
        "direct_answer": 10,
        "tool_call": 20,
        "workflow": 20,
    }
    assert report["observed_language_counts"] == {"en": 25, "zh": 25}
    per_action_language = Counter(
        (row["gold_request"]["action"]["type"], row["language"]) for row in first
    )
    assert per_action_language[("direct_answer", "en")] == 5
    assert per_action_language[("tool_call", "zh")] == 10


def test_summarize_e2e_condition_separates_execution_from_correctness(tmp_path: Path) -> None:
    gold_path = tmp_path / "gold.jsonl"
    run_path = tmp_path / "run.jsonl"
    gold_rows = _records()[:2]
    gold_path.write_text(
        "".join(json.dumps(row) + "\n" for row in gold_rows), encoding="utf-8"
    )
    runs = []
    for index, row in enumerate(gold_rows):
        prediction = row["gold_request"] if index == 0 else _request(row["id"], "direct_answer")
        prediction["action"]["answer"] = "wrong" if index else prediction["action"].get("answer")
        runs.append({
            "id": row["id"],
            "prediction": prediction,
            "execution": {
                "status": "succeeded",
                "result": {"execution_mode": "planner_only"},
            },
            "expert_invocation_count": 0,
            "timing": {"planner_ms": 10, "execution_ms": 1, "total_ms": 11},
        })
    run_path.write_text(
        "".join(json.dumps(row) + "\n" for row in runs), encoding="utf-8"
    )
    report = summarize_e2e_condition(gold_path, run_path, "test")
    assert report["execution_success_rate"] == 1.0
    assert report["routing_exact_rate"] == 0.5
    assert report["verified_e2e_correct_rate"] == 0.5
    assert report["task_output_correctness_available"] is False

    comparison = compare_e2e_conditions(
        gold_path,
        {
            "tool_observation_react": run_path,
            "glm46v_flash_toolspec": run_path,
            "vaguehydro_lora": run_path,
        },
        reference_condition="vaguehydro_lora",
    )
    assert comparison["condition_count"] == 3
    assert comparison["gold_count"] == 2
    assert comparison["reference_condition"] == "vaguehydro_lora"
    assert set(comparison["paired_significance_by_baseline"]) == {
        "tool_observation_react",
        "glm46v_flash_toolspec",
    }
    assert comparison["paired_significance_by_baseline"]["glm46v_flash_toolspec"][
        "routing_exact"
    ]["delta"] == 0.0
