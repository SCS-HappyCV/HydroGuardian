from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import hydro_remote_agent.evaluation.task_aware_e2e as task_aware_e2e
from hydro_remote_agent.evaluation.task_aware_e2e import evaluate_task_aware_conditions


def _request(request_id: str, action: dict, intent: str) -> dict:
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "intent": intent,
        "action": action,
        "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_task_aware_evaluation_scores_missing_output_as_zero(tmp_path: Path, monkeypatch) -> None:
    direct_id = "q:00-000001-attribute-3-1:direct:en:l0"
    mask_id = "q:00-000002-class-3-1:dense:zh:l2"
    direct_request = _request(
        direct_id,
        {"type": "direct_answer", "answer": "Yes. The target is present."},
        "attribute_judgement",
    )
    mask_request = _request(
        mask_id,
        {
            "type": "tool_call",
            "tool": "language_guided_point_segmentation",
            "arguments": {"image_path": "/i.png", "point_cloud_path": "/p.txt", "query": "road"},
        },
        "class_segmentation",
    )
    gold_rows = [
        {
            "id": direct_id,
            "sample_id": "00_000001",
            "language": "en",
            "ambiguity_level": "L0",
            "metadata": {"parent_query_id": "q:00-000001-attribute-3-1"},
            "gold_request": direct_request,
        },
        {
            "id": mask_id,
            "sample_id": "00_000002",
            "language": "zh",
            "ambiguity_level": "L2",
            "metadata": {"parent_query_id": "q:00-000002-class-3-1:dense"},
            "gold_request": mask_request,
        },
    ]
    gold_path = tmp_path / "gold.jsonl"
    _write_jsonl(gold_path, gold_rows)

    point_path = tmp_path / "data" / "00" / "velodyne" / "000002.txt"
    point_path.parent.mkdir(parents=True)
    np.savetxt(
        point_path,
        np.asarray([
            [0, 0, 0, 1, 1, 1, 3],
            [1, 0, 0, 1, 1, 1, 3],
            [2, 0, 0, 1, 1, 1, 9],
        ]),
    )
    annotation_path = tmp_path / "annotations.jsonl"
    _write_jsonl(annotation_path, [{
        "sample_id": "00_000002",
        "texts": [{
            "text_id": "00_000002_class_3_1",
            "task_type": "class",
            "target_label_ids": [3],
        }],
    }])

    mask_path = tmp_path / "target_mask.npz"
    np.savez_compressed(mask_path, target_mask=np.asarray([True, True, False]))
    candidate_rows = [
        {
            "id": direct_id,
            "condition": "vaguehydro_lora",
            "prediction": {
                **direct_request,
                "action": {"type": "direct_answer", "answer": "Yes, it is visible."},
            },
            "execution": {"status": "succeeded", "result": {"execution_mode": "planner_only"}},
        },
        {
            "id": mask_id,
            "condition": "vaguehydro_lora",
            "prediction": mask_request,
            "execution": {
                "status": "succeeded",
                "result": {"terminal_artifacts": {"target_mask": str(mask_path)}},
            },
        },
    ]
    baseline_rows = [
        {**candidate_rows[0], "condition": "tool_observation_react"},
        {
            "id": mask_id,
            "condition": "tool_observation_react",
            "prediction": mask_request,
            "execution": {"status": "failed", "error": "missing output"},
        },
    ]
    candidate_path = tmp_path / "candidate.jsonl"
    baseline_path = tmp_path / "baseline.jsonl"
    _write_jsonl(candidate_path, candidate_rows)
    _write_jsonl(baseline_path, baseline_rows)

    load_calls = 0
    original_load = task_aware_e2e._load_xyz_labels

    def counted_load(path: Path):
        nonlocal load_calls
        load_calls += 1
        return original_load(path)

    monkeypatch.setattr(task_aware_e2e, "_load_xyz_labels", counted_load)
    report = evaluate_task_aware_conditions(
        gold_path,
        {"tool_observation_react": baseline_path, "vaguehydro_lora": candidate_path},
        annotation_path,
        tmp_path / "data",
        tmp_path / "output",
        bootstrap_samples=100,
        bootstrap_seed=1,
    )
    assert report["condition_count"] == 2
    assert report["conditions"]["vaguehydro_lora"]["overall"]["mean_per_request_task_score"] == 1.0
    assert report["conditions"]["tool_observation_react"]["overall"]["mean_per_request_task_score"] == 0.5
    assert report["conditions"]["tool_observation_react"]["by_task_type"]["class"]["binary_mask"]["macro_iou"] == 0.0
    assert report["paired_comparison"]["mean_per_request_task_score"]["delta"] == 0.5
    assert load_calls == 1
