"""Offline proxy gate for Tool Increment Contribution Learning.

This experiment is deliberately conservative: the replacement CSV does not contain
an independent no-call trajectory, so it cannot validate the full TICL claim. It
only tests whether a multi-target replacement-impact predictor transfers better
than scalar and task-type baselines on held-out regions.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np


REQUEST_RE = re.compile(
    r"q:(?P<region>\d+)-(?P<frame>\d+)(?:-(?P<task>[^:]+))?:(?P<mode>[^:]+):(?P<language>[^:]+):l(?P<level>\d+)"
)


def parse_request_id(request_id: str) -> Dict[str, object]:
    match = REQUEST_RE.fullmatch(request_id)
    if match is None:
        return {"region": "unknown", "frame": -1, "task": "unknown", "mode": "unknown", "language": "unknown", "level": -1}
    groups = match.groupdict()
    task = groups["task"] or "unknown"
    return {
        "region": groups["region"],
        "frame": int(groups["frame"]),
        "task": task,
        "mode": groups["mode"],
        "language": groups["language"],
        "level": int(groups["level"]),
    }


def load_rows(path: Path, condition: str) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            if raw["condition"] != condition:
                continue
            if raw["after_execution_succeeded"] != "True":
                continue
            parsed = parse_request_id(raw["id"])
            before = float(raw["before_score"])
            after = float(raw["after_score"])
            parsed.update(
                {
                    "id": raw["id"],
                    "gold_action_type": raw["gold_action_type"],
                    "before_score": before,
                    "after_score": after,
                    "delta": after - before,
                    "large_change": float(abs(after - before) >= 0.10),
                    "cross_lambda": float((before >= 0.20) != (after >= 0.20)),
                }
            )
            rows.append(parsed)
    return rows


def make_features(train_rows: Sequence[Dict[str, object]], test_rows: Sequence[Dict[str, object]]) -> Tuple[np.ndarray, np.ndarray]:
    categorical = ["task", "mode", "language", "gold_action_type"]
    numeric = ["level", "before_score"]
    categories = {name: sorted({str(row[name]) for row in train_rows}) for name in categorical}

    def encode(rows: Sequence[Dict[str, object]]) -> np.ndarray:
        encoded = []
        for row in rows:
            values = []
            for name in categorical:
                values.extend(float(str(row[name]) == category) for category in categories[name])
            encoded.append(values)
        return np.asarray(encoded, dtype=float)

    train_cat = encode(train_rows)
    test_cat = encode(test_rows)
    train_num = np.asarray([[float(row[name]) for name in numeric] for row in train_rows])
    test_num = np.asarray([[float(row[name]) for name in numeric] for row in test_rows])
    mean = train_num.mean(axis=0)
    scale = np.maximum(train_num.std(axis=0), 1e-8)
    train_num = (train_num - mean) / scale
    test_num = (test_num - mean) / scale
    return np.concatenate([np.ones((len(train_rows), 1)), train_cat, train_num], axis=1), np.concatenate([np.ones((len(test_rows), 1)), test_cat, test_num], axis=1)


def ridge_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray, alpha: float = 1.0) -> np.ndarray:
    penalty = np.eye(x_train.shape[1]) * alpha
    penalty[0, 0] = 0.0
    weights = np.linalg.solve(x_train.T @ x_train + penalty, x_train.T @ y_train)
    return x_test @ weights


def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - predicted)))


def r2(actual: np.ndarray, predicted: np.ndarray) -> float:
    denominator = float(np.sum((actual - actual.mean()) ** 2))
    return float(1.0 - np.sum((actual - predicted) ** 2) / denominator) if denominator > 0 else 0.0


def task_mean_predict(train_rows: Sequence[Dict[str, object]], test_rows: Sequence[Dict[str, object]], target: str) -> np.ndarray:
    global_mean = float(np.mean([float(row[target]) for row in train_rows]))
    means = {}
    for task in {str(row["task"]) for row in train_rows}:
        values = [float(row[target]) for row in train_rows if row["task"] == task]
        means[task] = float(np.mean(values)) if values else global_mean
    return np.asarray([means.get(str(row["task"]), global_mean) for row in test_rows])


def evaluate_predictions(rows: Sequence[Dict[str, object]], predicted_after: np.ndarray, predicted_delta: np.ndarray) -> Dict[str, float]:
    actual_after = np.asarray([float(row["after_score"]) for row in rows])
    actual_delta = np.asarray([float(row["delta"]) for row in rows])
    predicted_call = predicted_delta > 0.02
    actual_call = actual_delta > 0.02
    return {
        "after_mae": mae(actual_after, predicted_after),
        "after_r2": r2(actual_after, predicted_after),
        "delta_mae": mae(actual_delta, predicted_delta),
        "delta_r2": r2(actual_delta, predicted_delta),
        "positive_delta_accuracy": float(np.mean(predicted_call == actual_call)),
        "cross_lambda_accuracy": float(
            np.mean((np.asarray([float(row["before_score"]) for row in rows]) >= 0.20) == (predicted_after >= 0.20))
        ),
    }


def run_gate(csv_path: Path, condition: str, train_regions: Sequence[str], test_regions: Sequence[str]) -> Dict[str, object]:
    rows = load_rows(csv_path, condition)
    train_rows = [row for row in rows if str(row["region"]) in train_regions]
    test_rows = [row for row in rows if str(row["region"]) in test_regions]
    if not train_rows or not test_rows:
        raise RuntimeError(f"Empty split for {condition}: train={len(train_rows)}, test={len(test_rows)}")

    x_train, x_test = make_features(train_rows, test_rows)
    y_train = np.asarray([[float(row["after_score"]), float(row["delta"]), float(row["large_change"]), float(row["cross_lambda"])] for row in train_rows])
    y_test = np.asarray([[float(row["after_score"]), float(row["delta"]), float(row["large_change"]), float(row["cross_lambda"])] for row in test_rows])

    scalar_after = ridge_predict(x_train, y_train[:, 0], x_test)
    scalar_delta = ridge_predict(x_train, y_train[:, 1], x_test)
    multi_prediction = ridge_predict(x_train, y_train, x_test)

    baseline_after = task_mean_predict(train_rows, test_rows, "after_score")
    baseline_delta = task_mean_predict(train_rows, test_rows, "delta")
    scalar_metrics = evaluate_predictions(test_rows, scalar_after, scalar_delta)
    multi_metrics = evaluate_predictions(test_rows, multi_prediction[:, 0], multi_prediction[:, 1])
    baseline_metrics = evaluate_predictions(test_rows, baseline_after, baseline_delta)
    return {
        "condition": condition,
        "train_regions": list(train_regions),
        "test_regions": list(test_regions),
        "train_count": len(train_rows),
        "test_count": len(test_rows),
        "baseline_task_mean": baseline_metrics,
        "scalar_ridge": scalar_metrics,
        "multi_target_ticl_proxy": multi_metrics,
        "limitations": [
            "No independent internal no-call trajectory is present in the replacement CSV.",
            "The target is replacement impact, so this is a proxy gate rather than full TICL validation.",
            "The held-out split is geographic/request-region transfer, not an unseen expert split.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=Path("runs/hydro_remote_agent/expert_replacement_v1/gufnet_m6_replay_v1/analysis/ptv3_to_gufnet_transitions.csv"))
    parser.add_argument("--condition", default="vaguehydro_lora")
    parser.add_argument("--train-regions", nargs="+", default=["00", "01"])
    parser.add_argument("--test-regions", nargs="+", default=["02"])
    parser.add_argument("--output", type=Path, default=Path("runs/hydro_remote_agent/ticl_gate_v1/proxy_gate.json"))
    args = parser.parse_args()
    result = run_gate(args.csv, args.condition, args.train_regions, args.test_regions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
