from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

import numpy as np


def binary_mask_metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float | int]:
    target = np.asarray(target, dtype=np.bool_).reshape(-1)
    prediction = np.asarray(prediction, dtype=np.bool_).reshape(-1)
    if target.shape != prediction.shape:
        raise ValueError(f"Mask lengths differ: {target.size} != {prediction.size}")
    intersection = int(np.count_nonzero(target & prediction))
    union = int(np.count_nonzero(target | prediction))
    target_count = int(np.count_nonzero(target))
    prediction_count = int(np.count_nonzero(prediction))
    denominator = target_count + prediction_count
    return {
        "intersection": intersection,
        "union": union,
        "target_points": target_count,
        "predicted_points": prediction_count,
        "iou": 1.0 if union == 0 else intersection / union,
        "dice": 1.0 if denominator == 0 else 2.0 * intersection / denominator,
    }


def _aggregate(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    succeeded = [row for row in rows if row.get("status") == "succeeded"]
    failed = [row for row in rows if row.get("status") != "succeeded"]
    intersections = sum(int(row["metrics"]["intersection"]) for row in succeeded)
    unions = sum(int(row["metrics"]["union"]) for row in succeeded)
    target_points = sum(int(row["metrics"]["target_points"]) for row in succeeded)
    predicted_points = sum(int(row["metrics"]["predicted_points"]) for row in succeeded)
    true_no_target = [row for row in succeeded if bool(row.get("is_no_target"))]
    predicted_no_target = [row for row in succeeded if bool(row.get("predicted_no_target"))]
    true_positive = sum(bool(row.get("predicted_no_target")) for row in true_no_target)
    false_positive = sum(
        bool(row.get("predicted_no_target")) and not bool(row.get("is_no_target"))
        for row in succeeded
    )
    false_negative = len(true_no_target) - true_positive
    no_target_precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else None
    no_target_recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else None
    no_target_f1 = (
        2 * no_target_precision * no_target_recall / (no_target_precision + no_target_recall)
        if no_target_precision is not None and no_target_recall is not None and no_target_precision + no_target_recall
        else None
    )
    latencies = [float(row["latency_ms"]) for row in succeeded]
    return {
        "request_count": len(rows),
        "succeeded_count": len(succeeded),
        "failed_count": len(failed),
        "macro_iou": float(np.mean([row["metrics"]["iou"] for row in succeeded])) if succeeded else None,
        "macro_dice": float(np.mean([row["metrics"]["dice"] for row in succeeded])) if succeeded else None,
        "micro_iou": 1.0 if unions == 0 else intersections / unions,
        "micro_dice": 1.0 if target_points + predicted_points == 0 else 2 * intersections / (target_points + predicted_points),
        "no_target_precision": no_target_precision,
        "no_target_recall": no_target_recall,
        "no_target_f1": no_target_f1,
        "abstention_accuracy": float(np.mean([
            bool(row.get("abstained")) == bool(row.get("is_no_target")) for row in succeeded
        ])) if succeeded else None,
        "mean_latency_ms": float(np.mean(latencies)) if latencies else None,
        "median_latency_ms": float(np.median(latencies)) if latencies else None,
        "failure_rate": len(failed) / len(rows) if rows else None,
        "predicted_no_target_count": len(predicted_no_target),
    }


def summarize_language_segmentation_rows(
    rows: Iterable[Mapping[str, Any]], expected_count: int
) -> dict[str, Any]:
    rows = list(rows)
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("task_type", "unknown"))].append(row)
    completed_ids = {str(row.get("request_id")) for row in rows if row.get("request_id")}
    overall = _aggregate(rows)
    report = {
        "schema_version": "vague_hydro.language_segmentation_eval.v1",
        "status": "completed" if len(completed_ids) == expected_count and overall["failed_count"] == 0 else "partial",
        "expected_count": expected_count,
        "completed_count": len(completed_ids),
        "overall": overall,
        "by_task_type": {name: _aggregate(group) for name, group in sorted(groups.items())},
        "failure_examples": [dict(row) for row in rows if row.get("status") != "succeeded"][:20],
    }
    threshold_names = sorted(
        {
            str(threshold)
            for row in rows
            for threshold in (row.get("threshold_metrics") or {})
        },
        key=float,
    )
    if threshold_names:
        threshold_sweep = {}
        for threshold in threshold_names:
            threshold_rows = []
            for row in rows:
                metrics = (row.get("threshold_metrics") or {}).get(threshold)
                if metrics is None:
                    continue
                threshold_row = dict(row)
                threshold_row["metrics"] = metrics
                threshold_rows.append(threshold_row)
            threshold_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
            for row in threshold_rows:
                threshold_groups[str(row.get("task_type", "unknown"))].append(row)
            threshold_sweep[threshold] = {
                "overall": _aggregate(threshold_rows),
                "by_task_type": {
                    name: _aggregate(group)
                    for name, group in sorted(threshold_groups.items())
                },
            }
        report["threshold_sweep"] = threshold_sweep
    return report
