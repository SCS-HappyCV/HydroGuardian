"""CPU kill gate for causal replacement credit.

The available replay contains paired PTv3/GUFNet outcomes but no new policy
training traces. This script therefore tests only whether paired delta
supervision improves held-out replacement prediction over absolute-score
supervision under identical features and model capacity.
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
    values = match.groupdict()
    return {
        "region": values["region"],
        "frame": int(values["frame"]),
        "task": values["task"] or "unknown",
        "mode": values["mode"],
        "language": values["language"],
        "level": int(values["level"]),
    }


def load_rows(path: Path, condition: str) -> List[Dict[str, object]]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            if raw["condition"] != condition or raw["after_execution_succeeded"] != "True":
                continue
            row = parse_request_id(raw["id"])
            row.update(
                {
                    "id": raw["id"],
                    "gold_action_type": raw["gold_action_type"],
                    "before_score": float(raw["before_score"]),
                    "after_score": float(raw["after_score"]),
                }
            )
            row["delta"] = row["after_score"] - row["before_score"]
            rows.append(row)
    return rows


def make_features(train_rows: Sequence[Dict[str, object]], rows: Sequence[Dict[str, object]]) -> Tuple[np.ndarray, List[str]]:
    categorical = ["task", "mode", "language", "gold_action_type"]
    numeric = ["level", "before_score"]
    categories = {name: sorted({str(row[name]) for row in train_rows}) for name in categorical}
    numeric_train = np.asarray([[float(row[name]) for name in numeric] for row in train_rows], dtype=float)
    mean = numeric_train.mean(axis=0)
    scale = np.maximum(numeric_train.std(axis=0), 1e-8)
    result = []
    for row in rows:
        values = [1.0]
        for name in categorical:
            values.extend(float(str(row[name]) == category) for category in categories[name])
        values.extend((float(row[name]) - mean[index]) / scale[index] for index, name in enumerate(numeric))
        result.append(values)
    names = ["bias"] + [f"{name}={category}" for name in categorical for category in categories[name]] + numeric
    return np.asarray(result, dtype=float), names


def ridge_predict(x_train: np.ndarray, target: np.ndarray, x_eval: np.ndarray, alpha: float = 1.0) -> np.ndarray:
    penalty = np.eye(x_train.shape[1]) * alpha
    penalty[0, 0] = 0.0
    weights = np.linalg.solve(x_train.T @ x_train + penalty, x_train.T @ target)
    return x_eval @ weights


def metrics(rows: Sequence[Dict[str, object]], predicted_after: np.ndarray, predicted_delta: np.ndarray) -> Dict[str, object]:
    actual_after = np.asarray([float(row["after_score"]) for row in rows])
    actual_delta = np.asarray([float(row["delta"]) for row in rows])
    actual_action = actual_after >= 0.20
    predicted_action = predicted_after >= 0.20
    by_task = {}
    for task in sorted({str(row["task"]) for row in rows}):
        indices = np.asarray([str(row["task"]) == task for row in rows])
        by_task[task] = {
            "count": int(indices.sum()),
            "after_mae": float(np.mean(np.abs(actual_after[indices] - predicted_after[indices]))),
            "delta_mae": float(np.mean(np.abs(actual_delta[indices] - predicted_delta[indices]))),
            "action_accuracy": float(np.mean(actual_action[indices] == predicted_action[indices])),
        }
    denominator = float(np.sum((actual_after - actual_after.mean()) ** 2))
    return {
        "after_mae": float(np.mean(np.abs(actual_after - predicted_after))),
        "after_r2": float(1.0 - np.sum((actual_after - predicted_after) ** 2) / denominator) if denominator else 0.0,
        "delta_mae": float(np.mean(np.abs(actual_delta - predicted_delta))),
        "action_accuracy_at_lambda_0.20": float(np.mean(actual_action == predicted_action)),
        "action_flip_count": int(np.sum(actual_action != (np.asarray([float(row["before_score"]) for row in rows]) >= 0.20))),
        "by_task": by_task,
    }


def run_gate(csv_path: Path, condition: str, train_regions: Sequence[str], test_regions: Sequence[str]) -> Dict[str, object]:
    rows = load_rows(csv_path, condition)
    train_rows = [row for row in rows if str(row["region"]) in train_regions]
    test_rows = [row for row in rows if str(row["region"]) in test_regions]
    if not train_rows or not test_rows:
        raise RuntimeError(f"Empty split: train={len(train_rows)}, test={len(test_rows)}")
    x_train, _ = make_features(train_rows, train_rows)
    x_test, _ = make_features(train_rows, test_rows)
    absolute_prediction = ridge_predict(
        x_train,
        np.asarray([float(row["after_score"]) for row in train_rows]),
        x_test,
    )
    delta_prediction = ridge_predict(
        x_train,
        np.asarray([float(row["delta"]) for row in train_rows]),
        x_test,
    )
    paired_after = np.asarray([float(row["before_score"]) for row in test_rows]) + delta_prediction
    result = {
        "condition": condition,
        "train_regions": list(train_regions),
        "test_regions": list(test_regions),
        "train_count": len(train_rows),
        "test_count": len(test_rows),
        "absolute_score_supervision": metrics(test_rows, absolute_prediction, absolute_prediction - np.asarray([float(row["before_score"]) for row in test_rows])),
        "paired_replacement_delta_supervision": metrics(test_rows, paired_after, delta_prediction),
        "limitations": [
            "No independent no-call trajectory is available; this is a replacement-credit proxy gate.",
            "The test region is held out geographically but the expert pair is fixed to PTv3/GUFNet.",
            "The model sees request metadata and PTv3 score, not expert identity or logits.",
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=Path("runs/hydro_remote_agent/expert_replacement_v1/gufnet_m6_replay_v1/analysis/ptv3_to_gufnet_transitions.csv"))
    parser.add_argument("--condition", default="vaguehydro_lora")
    parser.add_argument("--train-regions", nargs="+", default=["00", "01"])
    parser.add_argument("--test-regions", nargs="+", default=["02"])
    parser.add_argument("--output", type=Path, default=Path("runs/hydro_remote_agent/causal_replacement_credit_v1/gate.json"))
    args = parser.parse_args()
    result = run_gate(args.csv, args.condition, args.train_regions, args.test_regions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
