from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from hydro_remote_agent.tools.vaguehydro_preference_pilot_core import ROOT, load_freeze, sha256_file, verify_lock, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run_dir = ROOT / args.run_dir
    verify_lock(run_dir)
    cfg = load_freeze(run_dir)
    preflight = json.loads((run_dir / "PREFLIGHT_REPORT.json").read_text(encoding="utf-8"))
    pilot = json.loads((run_dir / "PILOT_REPORT.json").read_text(encoding="utf-8"))
    issues: list[str] = []
    checkpoint_manifest: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for arm in ("A", "B", "C"):
        for seed in cfg["seeds"]:
            report_path = run_dir / f"arm_{arm}" / f"seed_{seed}" / "ARM_SEED_REPORT.json"
            if not report_path.is_file():
                issues.append(f"missing report {report_path}")
                continue
            report = json.loads(report_path.read_text(encoding="utf-8"))
            reports.append(report)
            expected_steps = 0 if arm == "A" else int(cfg["optimization"]["max_optimizer_steps"])
            if report["optimizer_steps"] != expected_steps:
                issues.append(f"{arm}/{seed} optimizer steps mismatch")
            if report["frozen_240_reads"] != 0 or report["validation_used_for_tuning"]:
                issues.append(f"{arm}/{seed} leakage declaration failed")
            if arm == "A" and (report["adapter_changed"] or report["checkpoints"]):
                issues.append(f"A/{seed} unexpectedly changed or checkpointed")
            if arm in {"B", "C"}:
                if not report["adapter_changed"] or not report["checkpoint_resume_verified"]:
                    issues.append(f"{arm}/{seed} missing update/resume evidence")
                for checkpoint in report["checkpoints"]:
                    path = Path(checkpoint["path"])
                    files = {
                        "adapter_model.safetensors": checkpoint["adapter_sha256"],
                        "optimizer.pt": checkpoint["optimizer_sha256"],
                        "training_state.json": checkpoint["state_sha256"],
                    }
                    for name, expected_hash in files.items():
                        item = path / name
                        if not item.is_file():
                            issues.append(f"missing checkpoint file {item}")
                            continue
                        actual = sha256_file(item)
                        if actual != expected_hash:
                            issues.append(f"checkpoint hash mismatch {item}")
                        checkpoint_manifest.append({
                            "arm": arm, "seed": seed, "step": checkpoint["step"],
                            "path": str(item.relative_to(ROOT)), "bytes": item.stat().st_size,
                            "sha256": actual,
                        })
    execution = json.loads((run_dir / "EXECUTION_STATUS.json").read_text(encoding="utf-8"))
    completed_pairs = {(row.get("arm"), row.get("seed")) for row in execution if row.get("returncode") == 0}
    expected_pairs = {(arm, seed) for arm in ("A", "B", "C") for seed in cfg["seeds"]}
    if completed_pairs != expected_pairs:
        issues.append("execution status does not cover all nine successful arm/seed pairs")
    attempts = []
    for attempt in sorted(run_dir.glob("attempt*_failure")):
        attempts.append({
            "path": str(attempt.relative_to(ROOT)),
            "file_count": sum(1 for path in attempt.rglob("*") if path.is_file()),
            "readme_present": (attempt / "README_ATTEMPT.md").is_file(),
        })
    code_files = [
        "hydro_remote_agent/configs/vaguehydro_preference_training_pilot_v1.json",
        "hydro_remote_agent/tools/prepare_vaguehydro_preference_training_pilot_v1.py",
        "hydro_remote_agent/tools/vaguehydro_preference_pilot_core.py",
        "hydro_remote_agent/tools/preflight_vaguehydro_preference_training_pilot_v1.py",
        "hydro_remote_agent/tools/run_vaguehydro_preference_training_arm_v1.py",
        "hydro_remote_agent/tools/launch_vaguehydro_preference_training_pilot_v1.py",
        "hydro_remote_agent/tools/aggregate_vaguehydro_preference_training_pilot_v1.py",
        "hydro_remote_agent/tools/run_vaguehydro_preference_training_pilot_v1.sh",
        "hydro_remote_agent/rewards/completion_adapter.py",
        "hydro_remote_agent/rewards/gold_action_reward.py",
        "hydro_remote_agent/rewards/request_canonicalizer.py",
        "hydro_remote_agent/rewards/structural_contrast_reward.py",
        "hydro_remote_agent/rewards/structural_contrast_reward_v2.py",
        "hydro_remote_agent/schemas/agent_action.py",
        "hydro_remote_agent/schemas/tool_spec.py",
    ]
    execution_history: list[dict[str, Any]] = []
    for arm in ("A", "B", "C"):
        for seed in cfg["seeds"]:
            arm_dir = run_dir / f"arm_{arm}"
            exit_path = arm_dir / f"seed_{seed}.exit_code"
            stdout_path = arm_dir / f"seed_{seed}.stdout.log"
            stderr_path = arm_dir / f"seed_{seed}.stderr.log"
            report_path = arm_dir / f"seed_{seed}" / "ARM_SEED_REPORT.json"
            execution_history.append({
                "arm": arm,
                "seed": seed,
                "completed_report": report_path.is_file(),
                "completed_report_sha256": sha256_file(report_path) if report_path.is_file() else None,
                "exit_code": int(exit_path.read_text(encoding="utf-8").strip()) if exit_path.is_file() else None,
                "exit_code_sha256": sha256_file(exit_path) if exit_path.is_file() else None,
                "stdout_sha256": sha256_file(stdout_path) if stdout_path.is_file() else None,
                "stderr_sha256": sha256_file(stderr_path) if stderr_path.is_file() else None,
                "final_launcher_event": next((row for row in execution if row.get("arm") == arm and row.get("seed") == seed), None),
                "history_note": "A completed before the quarantined attempt2 evaluation failure and was retained; final resume skipped only its completed report." if arm == "A" else "Completed in final resumed launcher execution.",
            })
    write_json(run_dir / "EXECUTION_HISTORY.json", {
        "schema_version": "vaguehydro.preference_execution_history.v1",
        "all_nine_reports_complete": all(row["completed_report"] for row in execution_history),
        "all_nine_recorded_exit_codes_zero": all(row["exit_code"] == 0 for row in execution_history),
        "entries": execution_history,
    })
    evidence = {
        "schema_version": "vaguehydro.preference_pilot_integrity.v1",
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "preregistration_lock_verified": True,
        "preflight_pass": preflight.get("status") == "pass" and preflight.get("all_checks_pass") is True,
        "pilot_decision": pilot["decision"],
        "arm_seed_report_count": len(reports),
        "checkpoint_file_count": len(checkpoint_manifest),
        "checkpoint_manifest": checkpoint_manifest,
        "code_sha256": {name: sha256_file(ROOT / name) for name in code_files},
        "failed_attempts": attempts,
        "execution_history": "runs/hydro_remote_agent/vaguehydro_preference_training_pilot_v1/EXECUTION_HISTORY.json",
        "frozen_240_reads": 0,
        "formal_training_started": False,
        "validation_used_for_tuning": False,
    }
    write_json(run_dir / "INTEGRITY_EVIDENCE.json", evidence)
    print(json.dumps({"status": evidence["status"], "issues": len(issues), "checkpoint_files": len(checkpoint_manifest)}, sort_keys=True))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
