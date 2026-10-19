from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml

from hydro_remote_agent.evaluation.routing import iter_jsonl


def _ids(path: Path) -> set[str]:
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _sample_ids(path: Path) -> set[str]:
    return {str(row["sample_id"]) for _, row in iter_jsonl(path)}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _changed_ids(path: Path) -> set[str]:
    output = set()
    for _, row in iter_jsonl(path):
        marker = row.get("capability_policy")
        if isinstance(marker, Mapping) and marker.get("changed") is True:
            output.add(str(row["id"]))
    return output


def _artifact_paths(result: Mapping[str, Any]) -> list[str]:
    paths = []
    payload = result.get("result", {})
    groups = [payload.get("terminal_artifacts")]
    workflow = payload.get("workflow_result")
    if isinstance(workflow, Mapping):
        for step in workflow.get("steps", []):
            if isinstance(step, Mapping):
                groups.append((step.get("result") or {}).get("artifacts"))
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        for value in group.values():
            paths.extend(value if isinstance(value, list) else [value])
    return [str(value) for value in paths if isinstance(value, str)]


def audit(args) -> dict[str, Any]:
    train_ids, val_ids, test_ids = (_ids(args.train_split), _ids(args.val_split), _ids(args.test_split))
    calibration_ids = _sample_ids(args.calibration_manifest)
    test100_ids = _sample_ids(args.test_manifest)
    freeze = json.loads(args.freeze_report.read_text(encoding="utf-8"))
    policy = yaml.safe_load(args.policy.read_text(encoding="utf-8"))
    changed = _changed_ids(args.policy_predictions)
    replacement = {str(row["id"]): row for _, row in iter_jsonl(args.replacement_results)}
    artifact_paths = [path for row in replacement.values() for path in _artifact_paths(row)]
    checks = {
        "primary_splits_disjoint": not (train_ids & val_ids or train_ids & test_ids or val_ids & test_ids),
        "calibration_is_val_only": calibration_ids <= val_ids,
        "test100_is_test_only": test100_ids <= test_ids,
        "calibration_test100_overlap_zero": not (calibration_ids & test100_ids),
        "freeze_declares_no_test_consultation": freeze.get("test_results_consulted") is False,
        "freeze_baseline_hash_matches": freeze.get("baseline_report_sha256") == _sha256(args.baseline_val_report),
        "freeze_candidate_hash_matches": freeze.get("candidate_report_sha256") == _sha256(args.candidate_val_report),
        "policy_evidence_is_val_only": policy["rules"][0]["evidence"].get("calibration_split") == "val"
        and policy["rules"][0]["evidence"].get("test_results_consulted") is False,
        "changed_ids_equal_replacement_ids": changed == set(replacement),
        "all_replacements_succeeded": all(row.get("status") == "succeeded" for row in replacement.values()),
        "all_replacements_are_real": all(
            row.get("result", {}).get("execution_mode") == "expert_runtime"
            and not bool(row.get("result", {}).get("is_mock", False))
            for row in replacement.values()
        ),
        "all_artifacts_exist": bool(artifact_paths) and all(Path(path).is_file() for path in artifact_paths),
    }
    return {
        "schema_version": "cmge.policy_experiment_audit.v1",
        "status": "pass" if all(checks.values()) else "fail",
        "evaluation_type": "real_gt",
        "checks": checks,
        "counts": {
            "train_tiles": len(train_ids),
            "val_tiles": len(val_ids),
            "test_tiles": len(test_ids),
            "calibration_tiles": len(calibration_ids),
            "test100_tiles": len(test100_ids),
            "changed_requests": len(changed),
            "replacement_results": len(replacement),
            "artifact_paths": len(artifact_paths),
            "existing_artifact_paths": sum(Path(path).is_file() for path in artifact_paths),
        },
        "ground_truth_provenance": (
            "Dataset point labels (column 7) and manifest supervision rules; "
            "no model output is used as ground truth."
        ),
        "scope_note": "One fixed primary split, 60-tile validation calibration, and 100-tile held-out test evaluation.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mechanically audit the frozen CMGE policy experiment.")
    for name in (
        "train-split", "val-split", "test-split", "calibration-manifest", "test-manifest",
        "freeze-report", "policy", "baseline-val-report", "candidate-val-report",
        "policy-predictions", "replacement-results", "output",
    ):
        parser.add_argument(f"--{name}", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = audit(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
