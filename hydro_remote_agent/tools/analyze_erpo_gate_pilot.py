from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Mapping

import numpy as np


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze the paired ERPO gate pilot.")
    parser.add_argument("--candidate-a", required=True, type=Path)
    parser.add_argument("--candidate-b", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum-request-gain", type=float, default=0.05)
    parser.add_argument("--minimum-win-rate", type=float, default=0.25)
    parser.add_argument("--minimum-oracle-gain", type=float, default=0.03)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260820)
    return parser


def _load(path: Path) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            rows[str(row["id"])] = row
    return rows


def _bootstrap_ci(values: np.ndarray, samples: int, seed: int) -> List[float]:
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        draw = [values[rng.randrange(len(values))] for _ in range(len(values))]
        means.append(float(np.mean(draw)))
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def main() -> int:
    args = build_parser().parse_args()
    a = _load(args.candidate_a)
    b = _load(args.candidate_b)
    if set(a) != set(b):
        raise ValueError("Candidate score files do not contain the same request IDs")
    ids = sorted(a)
    scores_a = np.asarray([float(a[key]["task_score"]) for key in ids])
    scores_b = np.asarray([float(b[key]["task_score"]) for key in ids])
    delta = scores_b - scores_a
    better = delta >= args.minimum_request_gain
    oracle = np.maximum(scores_a, scores_b)
    win_rate = float(np.mean(better))
    oracle_gain = float(np.mean(oracle) - np.mean(scores_a))
    mean_delta = float(np.mean(delta))
    gate_passed = bool(
        win_rate >= args.minimum_win_rate
        and oracle_gain >= args.minimum_oracle_gain
    )
    strong_signal = bool(win_rate >= 0.30 and oracle_gain >= 0.08)
    report: Dict[str, Any] = {
        "schema_version": "erpo.gate_analysis.v1",
        "request_count": len(ids),
        "thresholds": {
            "minimum_request_gain": args.minimum_request_gain,
            "minimum_win_rate": args.minimum_win_rate,
            "minimum_oracle_gain": args.minimum_oracle_gain,
        },
        "candidate_a_mean_iou": float(np.mean(scores_a)),
        "candidate_b_mean_iou": float(np.mean(scores_b)),
        "candidate_b_minus_a": mean_delta,
        "candidate_b_minus_a_bootstrap_95ci": _bootstrap_ci(
            delta, args.bootstrap_samples, args.seed
        ),
        "candidate_b_win_count": int(np.count_nonzero(better)),
        "candidate_b_win_rate": win_rate,
        "candidate_a_win_count": int(np.count_nonzero(delta <= -args.minimum_request_gain)),
        "tie_or_small_difference_count": int(
            np.count_nonzero(np.abs(delta) < args.minimum_request_gain)
        ),
        "oracle_mean_iou": float(np.mean(oracle)),
        "oracle_gain_over_candidate_a": oracle_gain,
        "gate_passed": gate_passed,
        "strong_signal": strong_signal,
        "decision": (
            "proceed_to_erpo_training"
            if strong_signal
            else "proceed_to_larger_pilot"
            if gate_passed
            else "stop_erpo"
        ),
        "per_request": [
            {
                "id": key,
                "candidate_a_iou": float(scores_a[index]),
                "candidate_b_iou": float(scores_b[index]),
                "delta": float(delta[index]),
            }
            for index, key in enumerate(ids)
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in report.items() if key != "per_request"}, indent=2))
    return 0 if gate_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
