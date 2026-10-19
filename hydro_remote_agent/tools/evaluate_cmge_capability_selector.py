from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from hydro_remote_agent.evaluation.routing import iter_jsonl, parse_json_response


def _dense_scores(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for _, row in iter_jsonl(path):
        claim = row.get("claim")
        if isinstance(claim, Mapping) and int(claim.get("claim_index", -1)) == 1:
            rows[str(row["compound_id"])] = dict(row)
    return rows


def _request_features(prediction: Mapping[str, Any]) -> dict[str, Any]:
    request = parse_json_response(prediction.get("prediction"))
    action = request["action"]
    if action["type"] == "workflow":
        geometry = action["steps"][-1]["arguments"]
        return {
            "target_class_id": int(geometry["target_class_id"]),
            "reference_class_id": int(geometry["reference_class_id"]),
            "operation": str(geometry["operation"]),
        }
    target_ids = action["arguments"].get("target_class_ids", [])
    return {
        "target_class_id": int(target_ids[0]) if target_ids else -1,
        "reference_class_id": -1,
        "operation": "none",
    }


def build_paired_rows(
    predictions_path: Path,
    baseline_scores_path: Path,
    candidate_scores_path: Path,
) -> list[dict[str, Any]]:
    baseline = _dense_scores(baseline_scores_path)
    candidate = _dense_scores(candidate_scores_path)
    rows: list[dict[str, Any]] = []
    for _, prediction in iter_jsonl(predictions_path):
        compound_id = str(prediction["compound_id"])
        if compound_id not in baseline or compound_id not in candidate:
            raise ValueError(f"Missing paired score for {compound_id}")
        baseline_claim = baseline[compound_id]["claim"]
        candidate_claim = candidate[compound_id]["claim"]
        sample_id = str(baseline[compound_id]["sample_id"])
        row = {
            "id": str(prediction["id"]),
            "compound_id": compound_id,
            "sample_id": sample_id,
            "region": sample_id.split("_", 1)[0],
            "intent": str(prediction["intent"]),
            "baseline_iou": float(baseline_claim["iou"]),
            "candidate_iou": float(candidate_claim["iou"]),
            "baseline_predicted_points": int(baseline_claim["predicted_points"]),
            "candidate_predicted_points": int(candidate_claim["predicted_points"]),
        }
        row.update(_request_features(prediction))
        row["delta"] = row["candidate_iou"] - row["baseline_iou"]
        rows.append(row)
    return rows


def _feature_matrices(
    train_rows: Sequence[Mapping[str, Any]],
    eval_rows: Sequence[Mapping[str, Any]],
    include_observations: bool,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    categorical = ["intent", "target_class_id", "reference_class_id", "operation"]
    categories = {
        name: sorted({str(row[name]) for row in train_rows}) for name in categorical
    }
    numeric_names: list[str] = []
    if include_observations:
        numeric_names = ["baseline_log_points", "candidate_log_points", "log_point_ratio", "relative_point_delta"]

    def numeric(row: Mapping[str, Any]) -> list[float]:
        if not include_observations:
            return []
        baseline = float(row["baseline_predicted_points"])
        candidate = float(row["candidate_predicted_points"])
        baseline_log = float(np.log1p(baseline))
        candidate_log = float(np.log1p(candidate))
        return [
            baseline_log,
            candidate_log,
            candidate_log - baseline_log,
            (candidate - baseline) / max(candidate + baseline, 1.0),
        ]

    train_numeric = np.asarray([numeric(row) for row in train_rows], dtype=float)
    if include_observations:
        mean = train_numeric.mean(axis=0)
        scale = np.maximum(train_numeric.std(axis=0), 1e-8)
    else:
        mean = np.empty(0)
        scale = np.empty(0)

    def encode(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
        encoded = []
        for row in rows:
            values = [1.0]
            for name in categorical:
                values.extend(float(str(row[name]) == value) for value in categories[name])
            if include_observations:
                values.extend((np.asarray(numeric(row)) - mean) / scale)
            encoded.append(values)
        return np.asarray(encoded, dtype=float)

    names = ["bias"] + [
        f"{name}={value}" for name in categorical for value in categories[name]
    ] + numeric_names
    return encode(train_rows), encode(eval_rows), names


def _ridge_delta(
    train_rows: Sequence[Mapping[str, Any]],
    eval_rows: Sequence[Mapping[str, Any]],
    include_observations: bool,
    alpha: float,
) -> np.ndarray:
    x_train, x_eval, _ = _feature_matrices(train_rows, eval_rows, include_observations)
    target = np.asarray([float(row["delta"]) for row in train_rows])
    penalty = np.eye(x_train.shape[1]) * alpha
    penalty[0, 0] = 0.0
    weights = np.linalg.solve(x_train.T @ x_train + penalty, x_train.T @ target)
    return x_eval @ weights


def _metrics(rows: Sequence[Mapping[str, Any]], predicted_delta: np.ndarray) -> dict[str, Any]:
    baseline = np.asarray([float(row["baseline_iou"]) for row in rows])
    candidate = np.asarray([float(row["candidate_iou"]) for row in rows])
    choose_candidate = predicted_delta > 0.0
    selected = np.where(choose_candidate, candidate, baseline)
    oracle = np.maximum(baseline, candidate)
    actual_candidate_better = candidate > baseline
    return {
        "count": len(rows),
        "baseline_macro_iou": float(baseline.mean()),
        "candidate_macro_iou": float(candidate.mean()),
        "selected_macro_iou": float(selected.mean()),
        "oracle_macro_iou": float(oracle.mean()),
        "gain_over_baseline": float(selected.mean() - baseline.mean()),
        "oracle_gain_over_baseline": float(oracle.mean() - baseline.mean()),
        "regret_to_oracle": float(oracle.mean() - selected.mean()),
        "candidate_selection_count": int(choose_candidate.sum()),
        "selection_accuracy": float(np.mean(choose_candidate == actual_candidate_better)),
    }


def evaluate_selector(
    rows: Sequence[Mapping[str, Any]],
    train_regions: Sequence[str],
    test_regions: Sequence[str],
    alpha: float = 3.0,
    baseline_name: str = "gufnet",
    candidate_name: str = "ptv3",
) -> dict[str, Any]:
    train = [row for row in rows if str(row["region"]) in train_regions]
    test = [row for row in rows if str(row["region"]) in test_regions]
    if not train or not test:
        raise ValueError(f"Empty selector split: train={len(train)} test={len(test)}")
    request_prediction = _ridge_delta(train, test, include_observations=False, alpha=alpha)
    observation_prediction = _ridge_delta(train, test, include_observations=True, alpha=alpha)
    baseline_prediction = np.full(len(test), -1.0)
    candidate_prediction = np.full(len(test), 1.0)
    oracle_prediction = np.asarray([float(row["delta"]) for row in test])
    decisions = []
    for row, request_delta, observation_delta in zip(
        test, request_prediction, observation_prediction
    ):
        decisions.append(
            {
                "id": row["id"],
                "compound_id": row["compound_id"],
                "sample_id": row["sample_id"],
                "region": row["region"],
                "intent": row["intent"],
                "target_class_id": row["target_class_id"],
                "request_only_predicted_delta": float(request_delta),
                "dual_observation_predicted_delta": float(observation_delta),
                "request_only_expert": candidate_name if request_delta > 0 else baseline_name,
                "dual_observation_expert": candidate_name if observation_delta > 0 else baseline_name,
            }
        )
    return {
        "schema_version": "cmge.capability_selector_eval.v1",
        "train_regions": list(train_regions),
        "test_regions": list(test_regions),
        "train_count": len(train),
        "test_count": len(test),
        "ridge_alpha": alpha,
        "baseline_expert": baseline_name,
        "candidate_expert": candidate_name,
        "selectors": {
            "fixed_baseline": _metrics(test, baseline_prediction),
            "fixed_candidate": _metrics(test, candidate_prediction),
            "request_only_ridge": _metrics(test, request_prediction),
            "dual_observation_ridge": _metrics(test, observation_prediction),
            "oracle": _metrics(test, oracle_prediction),
        },
        "decisions": decisions,
        "limitations": [
            "The selector is calibrated on regions 00 and 01 and evaluated on held-out region 02.",
            "Dual-observation routing requires running both experts before selection and is a quality gate, not a compute-saving router.",
            "Only 54 paired replacement requests are available, so this is a feasibility gate rather than a final learned-selector result.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate CMGE capability-aware expert selection.")
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--baseline-scores", required=True, type=Path)
    parser.add_argument("--candidate-scores", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--decisions-output", required=True, type=Path)
    parser.add_argument("--train-regions", nargs="+", default=["00", "01"])
    parser.add_argument("--test-regions", nargs="+", default=["02"])
    parser.add_argument("--alpha", type=float, default=3.0)
    parser.add_argument("--baseline-name", default="gufnet")
    parser.add_argument("--candidate-name", default="ptv3")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    rows = build_paired_rows(args.predictions, args.baseline_scores, args.candidate_scores)
    report = evaluate_selector(
        rows,
        args.train_regions,
        args.test_regions,
        args.alpha,
        args.baseline_name,
        args.candidate_name,
    )
    decisions = report.pop("decisions")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.decisions_output.parent.mkdir(parents=True, exist_ok=True)
    args.decisions_output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in decisions),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
