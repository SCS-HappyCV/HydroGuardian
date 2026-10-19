from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml


CONDITION = "claimwise_rule_decomposition"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metrics(report: Mapping[str, Any]) -> tuple[float, dict[str, float], float]:
    row = report["conditions"][CONDITION]
    dense = row["dense"]
    return (
        float(dense["macro_iou"]),
        {str(key): float(value) for key, value in dense["by_intent_macro_iou"].items()},
        float(row["complete_request_correctness_iou_0_5"]),
    )


def decide_policy(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    minimum_overall_gain: float,
    maximum_subgroup_regression: float,
) -> dict[str, Any]:
    base_iou, base_groups, base_complete = _metrics(baseline)
    candidate_iou, candidate_groups, candidate_complete = _metrics(candidate)
    if set(base_groups) != set(candidate_groups):
        raise ValueError("Baseline and candidate intent groups must match")
    group_gains = {key: candidate_groups[key] - base_groups[key] for key in sorted(base_groups)}
    overall_gain = candidate_iou - base_iou
    passed = overall_gain >= minimum_overall_gain and min(group_gains.values()) >= -maximum_subgroup_regression
    return {
        "passed": passed,
        "decision": "freeze_source_capability_policy" if passed else "retain_source_expert",
        "baseline_macro_iou": base_iou,
        "candidate_macro_iou": candidate_iou,
        "overall_iou_gain": overall_gain,
        "subgroup_iou_gains": group_gains,
        "baseline_complete_correctness": base_complete,
        "candidate_complete_correctness": candidate_complete,
        "complete_correctness_gain": candidate_complete - base_complete,
        "minimum_overall_iou_gain": minimum_overall_gain,
        "maximum_subgroup_iou_regression": maximum_subgroup_regression,
    }


def freeze_policy(
    baseline_path: Path,
    candidate_path: Path,
    output_policy: Path,
    output_report: Path,
    minimum_overall_gain: float,
    maximum_subgroup_regression: float,
) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    decision = decide_policy(
        baseline, candidate, minimum_overall_gain, maximum_subgroup_regression
    )
    report = {
        "schema_version": "cmge.capability_policy_freeze.v1",
        "calibration_split": "val",
        "test_results_consulted": False,
        "baseline_report": str(baseline_path),
        "baseline_report_sha256": _sha256(baseline_path),
        "candidate_report": str(candidate_path),
        "candidate_report_sha256": _sha256(candidate_path),
        **decision,
    }
    output_report.parent.mkdir(parents=True, exist_ok=True)
    output_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not decision["passed"]:
        return report
    policy = {
        "schema_version": "cmge.capability_policy.v1",
        "policy_id": "cmge_language_call_ptv3_frozen_val_v1",
        "rules": [
            {
                "rule_id": "language_call_to_ptv3",
                "enabled": True,
                "source_tool": "language_guided_point_segmentation",
                "target_tool": "point_semantic_segmentation",
                "intents": [],
                "evidence": {
                    "calibration_split": "val",
                    "calibration_compound_count": int(baseline["compound_count"]),
                    "overall_iou_gain": decision["overall_iou_gain"],
                    "subgroup_iou_gains": decision["subgroup_iou_gains"],
                    "complete_correctness_gain": decision["complete_correctness_gain"],
                    "freeze_report": str(output_report),
                    "test_results_consulted": False,
                },
            }
        ],
    }
    output_policy.parent.mkdir(parents=True, exist_ok=True)
    output_policy.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze a CMGE capability policy using validation evidence only.")
    parser.add_argument("--baseline-report", required=True, type=Path)
    parser.add_argument("--candidate-report", required=True, type=Path)
    parser.add_argument("--output-policy", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    parser.add_argument("--minimum-overall-gain", type=float, default=0.02)
    parser.add_argument("--maximum-subgroup-regression", type=float, default=0.02)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = freeze_policy(
        args.baseline_report,
        args.candidate_report,
        args.output_policy,
        args.output_report,
        args.minimum_overall_gain,
        args.maximum_subgroup_regression,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
