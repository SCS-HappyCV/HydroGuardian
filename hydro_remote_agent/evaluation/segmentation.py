from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np


CLASS_NAMES = (
    "Shed",
    "Concretehouse",
    "Cementroad",
    "Dirtroad",
    "Slope",
    "Scarp",
    "Dam",
    "Vegetablefield",
    "Grassland",
    "Dryland",
    "Woodland",
    "Bareland",
    "Waterline",
    "Ditch",
    "Others",
)


def confusion_matrix_1based(
    ground_truth: np.ndarray,
    prediction: np.ndarray,
    num_classes: int = 15,
) -> np.ndarray:
    ground_truth = np.asarray(ground_truth).reshape(-1)
    prediction = np.asarray(prediction).reshape(-1)
    if ground_truth.shape != prediction.shape:
        raise ValueError(
            f"Ground truth and prediction lengths differ: {len(ground_truth)} != {len(prediction)}"
        )
    valid = (
        (ground_truth >= 1)
        & (ground_truth <= num_classes)
        & (prediction >= 1)
        & (prediction <= num_classes)
    )
    encoded = (ground_truth[valid].astype(np.int64) - 1) * num_classes
    encoded += prediction[valid].astype(np.int64) - 1
    return np.bincount(encoded, minlength=num_classes * num_classes).reshape(
        num_classes, num_classes
    )


def segmentation_metrics(confusion: np.ndarray) -> dict[str, Any]:
    confusion = np.asarray(confusion, dtype=np.int64)
    if confusion.ndim != 2 or confusion.shape[0] != confusion.shape[1]:
        raise ValueError("Confusion matrix must be square")
    true_positive = np.diag(confusion).astype(np.float64)
    ground_truth = confusion.sum(axis=1).astype(np.float64)
    predicted = confusion.sum(axis=0).astype(np.float64)
    union = ground_truth + predicted - true_positive
    iou = np.divide(
        true_positive,
        union,
        out=np.full_like(true_positive, np.nan),
        where=union > 0,
    )
    class_accuracy = np.divide(
        true_positive,
        ground_truth,
        out=np.full_like(true_positive, np.nan),
        where=ground_truth > 0,
    )
    total = int(confusion.sum())
    class_names = CLASS_NAMES if len(confusion) == len(CLASS_NAMES) else tuple(
        f"class_{index + 1}" for index in range(len(confusion))
    )
    per_class = []
    for index, name in enumerate(class_names):
        per_class.append(
            {
                "class_id": index + 1,
                "class_name": name,
                "iou": None if np.isnan(iou[index]) else float(iou[index]),
                "accuracy": (
                    None if np.isnan(class_accuracy[index]) else float(class_accuracy[index])
                ),
                "ground_truth_points": int(ground_truth[index]),
                "predicted_points": int(predicted[index]),
            }
        )
    return {
        "mean_iou": None if np.isnan(iou).all() else float(np.nanmean(iou)),
        "mean_accuracy": (
            None if np.isnan(class_accuracy).all() else float(np.nanmean(class_accuracy))
        ),
        "overall_accuracy": None if total == 0 else float(true_positive.sum() / total),
        "evaluated_points": total,
        "evaluated_class_count": int(np.sum(~np.isnan(iou))),
        "per_class": per_class,
    }


def summarize_segmentation_rows(
    rows: Iterable[Mapping[str, Any]],
    expected_count: int,
) -> dict[str, Any]:
    rows = list(rows)
    succeeded = [row for row in rows if row.get("status") == "succeeded"]
    failed = [row for row in rows if row.get("status") != "succeeded"]
    confusion = np.zeros((15, 15), dtype=np.int64)
    for row in succeeded:
        candidate = np.asarray(row["confusion_matrix"], dtype=np.int64)
        if candidate.shape != confusion.shape:
            raise ValueError(f"Invalid confusion matrix for {row.get('sample_id')}")
        confusion += candidate
    metrics = segmentation_metrics(confusion)
    latencies = [float(row["latency_ms"]) for row in succeeded]
    metrics["mean_latency_ms"] = float(np.mean(latencies)) if latencies else None
    metrics["median_latency_ms"] = float(np.median(latencies)) if latencies else None
    completed_count = len({str(row.get("sample_id")) for row in rows})
    status = "completed" if completed_count == expected_count and not failed else "partial"
    return {
        "schema_version": "vague_hydro.segmentation_eval.v1",
        "status": status,
        "expected_count": expected_count,
        "completed_count": completed_count,
        "succeeded_count": len(succeeded),
        "failed_count": len(failed),
        "failure_examples": [dict(row) for row in failed[:20]],
        "metrics": metrics,
        "confusion_matrix": confusion.tolist(),
    }


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
    return rows
