from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

import numpy as np


def _runtime_task_type(row: Mapping[str, Any]) -> str:
    runtime_type = row.get("runtime_task_type")
    if runtime_type in {"class", "attribute", "relation"}:
        return str(runtime_type)
    source_type = str(row.get("task_type", "unknown"))
    return "class" if source_type == "no_target" else source_type


def select_mask_thresholds(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, list[Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get("status") != "succeeded" or bool(row.get("is_no_target")):
            continue
        task_type = _runtime_task_type(row)
        for threshold, metrics in (row.get("threshold_metrics") or {}).items():
            grouped[task_type][str(threshold)].append(metrics)

    report = {}
    for task_type, threshold_groups in sorted(grouped.items()):
        candidates = []
        for threshold, metrics_list in threshold_groups.items():
            intersections = sum(int(item["intersection"]) for item in metrics_list)
            unions = sum(int(item["union"]) for item in metrics_list)
            candidate = {
                "threshold": float(threshold),
                "request_count": len(metrics_list),
                "macro_iou": float(np.mean([float(item["iou"]) for item in metrics_list])),
                "macro_dice": float(np.mean([float(item["dice"]) for item in metrics_list])),
                "micro_iou": 1.0 if unions == 0 else intersections / unions,
            }
            candidates.append(candidate)
        candidates.sort(key=lambda item: item["threshold"])
        best = max(
            candidates,
            key=lambda item: (item["macro_iou"], item["micro_iou"], -abs(item["threshold"] - 0.5)),
        )
        report[task_type] = {"best": best, "candidates": candidates}
    return report


def _candidate_thresholds(values: np.ndarray, max_count: int = 101) -> np.ndarray:
    unique = np.unique(values.astype(np.float64))
    if unique.size <= max_count:
        return unique
    return np.unique(np.quantile(unique, np.linspace(0.0, 1.0, max_count)))


def _classification_metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float | int]:
    target = target.astype(np.bool_)
    prediction = prediction.astype(np.bool_)
    tp = int(np.count_nonzero(target & prediction))
    fp = int(np.count_nonzero(~target & prediction))
    fn = int(np.count_nonzero(target & ~prediction))
    tn = int(np.count_nonzero(~target & ~prediction))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": (tp + tn) / max(len(target), 1),
    }


def calibrate_no_target(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row.get("status") == "succeeded" and _runtime_task_type(row) == "class"
    ]
    required = ("posterior_no_target_mass", "abstain_probability", "probability_max")
    selected = [row for row in selected if all((row.get("diagnostics") or {}).get(key) is not None for key in required)]
    if not selected:
        return {"request_count": 0, "best_rule": None, "candidates": []}

    target = np.asarray([bool(row.get("is_no_target")) for row in selected], dtype=np.bool_)
    posterior = np.asarray([float(row["diagnostics"]["posterior_no_target_mass"]) for row in selected])
    abstain = np.asarray([float(row["diagnostics"]["abstain_probability"]) for row in selected])
    probability_max = np.asarray([float(row["diagnostics"]["probability_max"]) for row in selected])
    candidates = []

    def add(rule: dict[str, Any], prediction: np.ndarray) -> None:
        candidates.append({"rule": rule, "metrics": _classification_metrics(target, prediction)})

    posterior_thresholds = _candidate_thresholds(posterior)
    abstain_thresholds = _candidate_thresholds(abstain)
    probability_thresholds = _candidate_thresholds(probability_max)
    for threshold in posterior_thresholds:
        add({"type": "posterior_gte", "posterior_no_target_mass": float(threshold)}, posterior >= threshold)
    for threshold in abstain_thresholds:
        add({"type": "abstain_gte", "abstain_probability": float(threshold)}, abstain >= threshold)
    for threshold in probability_thresholds:
        add({"type": "probability_max_lte", "probability_max": float(threshold)}, probability_max <= threshold)
    for posterior_threshold in posterior_thresholds:
        posterior_hit = posterior >= posterior_threshold
        for probability_threshold in probability_thresholds:
            add(
                {
                    "type": "posterior_gte_and_probability_max_lte",
                    "posterior_no_target_mass": float(posterior_threshold),
                    "probability_max": float(probability_threshold),
                },
                posterior_hit & (probability_max <= probability_threshold),
            )

    candidates.sort(
        key=lambda item: (
            item["metrics"]["f1"],
            item["metrics"]["precision"],
            item["metrics"]["accuracy"],
            -len(item["rule"]),
        ),
        reverse=True,
    )
    return {
        "request_count": len(selected),
        "positive_count": int(target.sum()),
        "negative_count": int((~target).sum()),
        "best_rule": candidates[0] if candidates else None,
        "top_candidates": candidates[:20],
    }
