from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from hydro_remote_agent.evaluation.routing import iter_jsonl


def _load(path: Path) -> dict[str, dict[str, Any]]:
    compounds: dict[str, dict[str, Any]] = defaultdict(dict)
    for _, row in iter_jsonl(path):
        claim = row["claim"]
        key = "direct" if int(claim["claim_index"]) == 0 else "dense"
        compounds[str(row["compound_id"])][key] = dict(claim)
    invalid = [key for key, value in compounds.items() if set(value) != {"direct", "dense"}]
    if invalid:
        raise ValueError(f"Incomplete scored compounds: {invalid[:5]}")
    return dict(compounds)


def _arrays(rows: Mapping[str, Mapping[str, Any]], ids: Sequence[str]):
    iou = np.asarray([float(rows[key]["dense"]["iou"]) for key in ids], dtype=np.float64)
    direct = np.asarray([bool(rows[key]["direct"]["semantic_correct"]) for key in ids])
    complete = direct & (iou >= 0.5)
    intents = [str(rows[key]["dense"]["canonical_intent"]) for key in ids]
    return iou, complete, intents


def _summary(iou: np.ndarray, complete: np.ndarray, intents: Sequence[str]) -> dict[str, Any]:
    groups: dict[str, list[float]] = defaultdict(list)
    for value, intent in zip(iou, intents):
        groups[intent].append(float(value))
    return {
        "dense_macro_iou": float(np.mean(iou)),
        "complete_correctness_iou_0_5": float(np.mean(complete)),
        "by_intent_macro_iou": {
            key: float(np.mean(values)) for key, values in sorted(groups.items())
        },
    }


def _bootstrap_difference(
    candidate: np.ndarray, baseline: np.ndarray, samples: int, seed: int
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    difference = candidate - baseline
    indices = rng.integers(0, difference.size, size=(samples, difference.size))
    estimates = difference[indices].mean(axis=1)
    return {
        "mean_difference": float(difference.mean()),
        "ci95": [float(value) for value in np.quantile(estimates, [0.025, 0.975])],
        "one_sided_bootstrap_p": float((np.count_nonzero(estimates <= 0) + 1) / (samples + 1)),
        "win_tie_loss": {
            "win": int(np.count_nonzero(difference > 0)),
            "tie": int(np.count_nonzero(difference == 0)),
            "loss": int(np.count_nonzero(difference < 0)),
        },
    }


def _mcnemar(candidate: np.ndarray, baseline: np.ndarray) -> dict[str, Any]:
    candidate_only = int(np.count_nonzero(candidate & ~baseline))
    baseline_only = int(np.count_nonzero(baseline & ~candidate))
    discordant = candidate_only + baseline_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, value) for value in range(min(candidate_only, baseline_only) + 1))
        p_value = min(1.0, 2.0 * tail / (2**discordant))
    return {
        "candidate_only_correct": candidate_only,
        "baseline_only_correct": baseline_only,
        "discordant_count": discordant,
        "exact_two_sided_p": float(p_value),
    }


def analyze(
    baseline_path: Path,
    intent_path: Path,
    source_path: Path,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    rows = {
        "baseline": _load(baseline_path),
        "intent_only": _load(intent_path),
        "source_capability": _load(source_path),
    }
    id_sets = {name: set(value) for name, value in rows.items()}
    if len({frozenset(value) for value in id_sets.values()}) != 1:
        raise ValueError("All conditions must contain the same compound IDs")
    ids = sorted(id_sets["baseline"])
    arrays = {name: _arrays(value, ids) for name, value in rows.items()}
    base_iou, base_complete, intents = arrays["baseline"]
    source_iou, source_complete, source_intents = arrays["source_capability"]
    if intents != source_intents:
        raise ValueError("Intent labels changed across conditions")
    oracle_iou = np.maximum(base_iou, source_iou)
    direct_correct = np.asarray(
        [bool(rows["baseline"][key]["direct"]["semantic_correct"]) for key in ids]
    )
    oracle_complete = direct_correct & (oracle_iou >= 0.5)
    conditions = {
        name: _summary(values[0], values[1], values[2])
        for name, values in arrays.items()
    }
    conditions["oracle"] = _summary(oracle_iou, oracle_complete, intents)

    comparisons = {}
    for candidate_name, baseline_name in (
        ("intent_only", "baseline"),
        ("source_capability", "baseline"),
        ("source_capability", "intent_only"),
        ("oracle", "source_capability"),
    ):
        candidate_iou, candidate_complete = (
            (oracle_iou, oracle_complete)
            if candidate_name == "oracle"
            else arrays[candidate_name][:2]
        )
        comparison_iou, comparison_complete = arrays[baseline_name][:2]
        comparisons[f"{candidate_name}_vs_{baseline_name}"] = {
            "dense_iou": _bootstrap_difference(
                candidate_iou, comparison_iou, bootstrap_samples, seed
            ),
            "complete_correctness": {
                "difference": float(candidate_complete.mean() - comparison_complete.mean()),
                "mcnemar": _mcnemar(candidate_complete, comparison_complete),
            },
        }
    return {
        "schema_version": "cmge.policy_ablation_analysis.v1",
        "compound_count": len(ids),
        "paired_by_compound_id": True,
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": seed,
        "conditions": conditions,
        "comparisons": comparisons,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze frozen CMGE policy ablations.")
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--intent-only", required=True, type=Path)
    parser.add_argument("--source-capability", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260826)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = analyze(
        args.baseline,
        args.intent_only,
        args.source_capability,
        args.bootstrap_samples,
        args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
