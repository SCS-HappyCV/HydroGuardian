from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summary(values: Sequence[float]) -> dict[str, float]:
    return {
        "mean": statistics.fmean(values),
        "std": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate VagueHydro-R M4 multi-seed pilot reports.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    freeze_path = args.freeze if args.freeze.is_absolute() else root / args.freeze
    freeze = read_json(freeze_path)
    parent = freeze_path.parent
    reports = []
    for seed in freeze["seeds"]:
        seed_dir = parent / f"seed_{seed}"
        report_path = seed_dir / "SEED_REPORT.json"
        if report_path.is_file():
            seed_report = read_json(report_path)
            seal_exit_path = seed_dir / "seal.exit_code"
            seed_report["seal_exit_code"] = (
                int(seal_exit_path.read_text().strip()) if seal_exit_path.is_file() else None
            )
            seed_report["pilot_seed_pass"] = bool(seed_report["pilot_seed_pass"]) and seed_report[
                "seal_exit_code"
            ] == 0
            reports.append(seed_report)
            continue
        train_exit_path = seed_dir / "train.exit_code"
        seal_exit_path = seed_dir / "seal.exit_code"
        reports.append(
            {
                "seed": int(seed),
                "status": "blocked",
                "pilot_seed_pass": False,
                "train_exit_code": int(train_exit_path.read_text().strip()) if train_exit_path.is_file() else None,
                "seal_exit_code": int(seal_exit_path.read_text().strip()) if seal_exit_path.is_file() else None,
                "rewards": {"mean": 0.0, "std": 0.0},
                "quality": {"invalid_parse_rate": 1.0, "clipping_rate": 1.0},
                "gpu": {"peak_memory_gib": 0.0},
                "training": {"train_loss": 0.0},
                "gaps": ["SEED_REPORT.json was not produced; inspect seed stderr and seal stderr."],
            }
        )
    pass_count = sum(report["pilot_seed_pass"] for report in reports)
    if pass_count == len(reports):
        status = "pass"
    elif pass_count:
        status = "partial"
    else:
        status = "blocked"
    metrics = {
        "reward_mean": summary([float(report["rewards"]["mean"]) for report in reports]),
        "reward_std": summary([float(report["rewards"]["std"]) for report in reports]),
        "invalid_parse_rate": summary([float(report["quality"]["invalid_parse_rate"]) for report in reports]),
        "clipping_rate": summary([float(report["quality"]["clipping_rate"]) for report in reports]),
        "peak_gpu_memory_gib": summary([float(report["gpu"]["peak_memory_gib"]) for report in reports]),
        "train_loss": summary([float(report["training"]["train_loss"]) for report in reports]),
    }
    ready_for_formal = status == "pass" and metrics["clipping_rate"]["max"] < 0.10
    if status != "pass":
        recommendation = "Do not start formal multi-seed GRPO; at least one pilot seed failed its integrity gate."
    elif not ready_for_formal:
        recommendation = "Hold formal multi-seed GRPO until completion clipping is reduced below the pilot threshold."
    else:
        recommendation = "READY_FOR_FORMAL_MULTISEED_GRPO"
    gaps = []
    for report in reports:
        gaps.extend(f"Seed {report['seed']}: {gap}" for gap in report.get("gaps", []))
    if metrics["clipping_rate"]["max"] >= 0.10:
        gaps.append("At least one seed fails the strict clipping-rate <10% pilot threshold.")
    if metrics["invalid_parse_rate"]["mean"] > 0.0:
        gaps.append("Invalid policy completions remain and must be monitored during formal training.")
    attempt0 = parent / "attempt0_eager_8192_scan"
    run_disclosures = []
    if attempt0.is_dir():
        run_disclosures.append(
            {
                "attempt": attempt0.name,
                "status": "manually_stopped_before_first_optimizer_step",
                "reason": "Eagerly copying the top-8192 vocabulary candidates to CPU made token-by-token generation impractically slow.",
                "result_reuse": False,
                "checkpoint_created": False,
                "replacement": "Dynamic top-512 scan with fallback to the frozen top-8192 cap only when no legal token is found.",
                "evidence": str(
                    (attempt0 / "seed_20261011" / "stderr.log").relative_to(root)
                ),
            }
        )
    report = {
        "schema_version": "vaguehydro_r.m4_multiseed_pilot_report.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "pilot_pass": status == "pass",
        "ready_for_formal_multiseed_grpo": ready_for_formal,
        "recommendation": recommendation,
        "launch_decision": "do_not_auto_start_formal_training",
        "scope": "three-seed short pilot only; no final task-quality claim",
        "seeds": [int(value) for value in freeze["seeds"]],
        "seed_pass_count": pass_count,
        "seed_count": len(reports),
        "seed_reports": reports,
        "aggregate_metrics": metrics,
        "frozen_test_samples": 0,
        "called_real_experts": False,
        "called_verifier": False,
        "decoder_runtime": {
            "initial_scan_top_tokens": 512,
            "fallback_scan_cap": int(freeze["sampling"]["constraint_scan_top_tokens"]),
            "fallback_condition": "no legal token found in initial scan",
        },
        "artifact_retention": "Large trainer checkpoints and optimizer states are retained on the remote host; reports record remote path, byte count, and SHA-256.",
        "run_disclosures": run_disclosures,
        "gaps": gaps,
    }
    write_json(parent / "M4_REPORT.json", report)
    (parent / "M4_REPORT.md").write_text(
        "\n".join(
            [
                "# VagueHydro-R M4 Multi-Seed Pilot",
                "",
                f"- Status: **{status.upper()}**",
                f"- Seeds passed: `{pass_count}/{len(reports)}`",
                f"- Ready for formal multi-seed GRPO: `{ready_for_formal}`",
                f"- Reward mean across seeds: `{metrics['reward_mean']['mean']}` ± `{metrics['reward_mean']['std']}`",
                f"- Invalid parse rate: `{metrics['invalid_parse_rate']['mean']}` ± `{metrics['invalid_parse_rate']['std']}`",
                f"- Clipping rate: `{metrics['clipping_rate']['mean']}` ± `{metrics['clipping_rate']['std']}`",
                f"- Peak GPU GiB: `{metrics['peak_gpu_memory_gib']['mean']}` ± `{metrics['peak_gpu_memory_gib']['std']}`",
                "- Frozen-test samples: `0`",
                "- Real experts / Verifier: `False / False`",
                "- Decoder scan: dynamic `top-512`, falling back to the frozen `top-8192` cap only when no legal token is found",
                "- Large checkpoint/optimizer binaries: retained remotely with path, byte count, and SHA-256 in each seed report",
                "",
                f"Recommendation: {recommendation}",
                "",
                *(
                    [
                        "## Run Disclosure",
                        "",
                        "- `attempt0_eager_8192_scan` was manually stopped before the first optimizer step because eager top-8192 CPU scanning was impractically slow.",
                        "- No attempt0 checkpoint, optimizer state, candidate result, or reward result was reused.",
                        "- The completed run uses dynamic top-512 scanning with fallback to the unchanged top-8192 cap.",
                        "",
                    ]
                    if run_disclosures
                    else []
                ),
                "This is a short pilot, not formal training or final task-quality evidence.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (parent / "GAP_LIST.md").write_text(
        "# VagueHydro-R M4 Gap List\n\n" + ("\n".join(f"- {gap}" for gap in gaps) if gaps else "- None for the pilot gate.") + "\n",
        encoding="utf-8",
    )
    print(status)
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
