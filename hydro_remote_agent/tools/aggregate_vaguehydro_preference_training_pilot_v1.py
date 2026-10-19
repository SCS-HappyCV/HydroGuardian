from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from hydro_remote_agent.tools.vaguehydro_preference_pilot_core import ROOT, load_freeze, verify_lock, write_json


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    fields = {
        "pair_accuracy": [r["evaluation"]["heldout_pair_preference"]["accuracy"] for r in reports],
        "pair_margin": [r["evaluation"]["heldout_pair_preference"]["mean_margin"] for r in reports],
        "heldout_legality": [r["evaluation"]["heldout_source_generation"]["strict_legality_rate"] for r in reports],
        "heldout_reward_a": [r["evaluation"]["heldout_source_generation"]["reward_a"]["total"] for r in reports],
        "heldout_reward_b": [r["evaluation"]["heldout_source_generation"]["reward_b"]["total"] for r in reports],
        "m1_legality": [r["evaluation"]["m1_validation_regression"]["strict_legality_rate"] for r in reports],
        "m1_reward_a": [r["evaluation"]["m1_validation_regression"]["reward_a"]["total"] for r in reports],
        "m1_reward_b": [r["evaluation"]["m1_validation_regression"]["reward_b"]["total"] for r in reports],
        "equivalence_preservation": [r["evaluation"]["equivalence_preservation"]["preservation_rate"] for r in reports],
    }
    return {
        key: {"values": values, "mean": mean(values), "sample_std": statistics.stdev(values) if len(values) > 1 else 0.0}
        for key, values in fields.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run_dir = ROOT / args.run_dir
    verify_lock(run_dir)
    cfg = load_freeze(run_dir)
    reports: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ("A", "B", "C")}
    for arm in reports:
        for seed in cfg["seeds"]:
            path = run_dir / f"arm_{arm}" / f"seed_{seed}" / "ARM_SEED_REPORT.json"
            if not path.is_file():
                raise FileNotFoundError(f"missing preregistered arm/seed report: {path}")
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("status") != "pass" or report.get("frozen_240_reads") != 0:
                raise ValueError(f"invalid report status or frozen access: {path}")
            reports[arm].append(report)
    summaries = {arm: summary(items) for arm, items in reports.items()}
    baseline = {r["seed"]: r for r in reports["A"]}
    gates: dict[str, Any] = {}
    for arm in ("B", "C"):
        seed_checks = []
        for report in reports[arm]:
            control = baseline[report["seed"]]
            pair = report["evaluation"]["heldout_pair_preference"]
            control_pair = control["evaluation"]["heldout_pair_preference"]
            margin_delta = pair["mean_margin"] - control_pair["mean_margin"]
            accuracy_delta = pair["accuracy"] - control_pair["accuracy"]
            legality_delta = report["evaluation"]["heldout_source_generation"]["strict_legality_rate"] - control["evaluation"]["heldout_source_generation"]["strict_legality_rate"]
            m1_reward_delta = report["evaluation"]["m1_validation_regression"]["reward_a"]["total"] - control["evaluation"]["m1_validation_regression"]["reward_a"]["total"]
            m1_legality_delta = report["evaluation"]["m1_validation_regression"]["strict_legality_rate"] - control["evaluation"]["m1_validation_regression"]["strict_legality_rate"]
            preference_pass = margin_delta >= cfg["release_gates"]["paired_margin_improvement_min"] or accuracy_delta >= cfg["release_gates"]["or_pair_accuracy_improvement_min"]
            seed_checks.append({
                "seed": report["seed"], "margin_delta": margin_delta, "accuracy_delta": accuracy_delta,
                "heldout_legality_delta": legality_delta, "m1_reward_a_delta": m1_reward_delta,
                "m1_legality_delta": m1_legality_delta, "preference_improvement": preference_pass,
                "legality_non_degradation": legality_delta >= -cfg["release_gates"]["strict_legality_drop_max"],
                "m1_reward_non_regression": m1_reward_delta >= -cfg["release_gates"]["m1_reward_a_drop_max"],
                "m1_legality_non_regression": m1_legality_delta >= -cfg["release_gates"]["m1_legality_drop_max"],
            })
        mean_margin_delta = summaries[arm]["pair_margin"]["mean"] - summaries["A"]["pair_margin"]["mean"]
        mean_accuracy_delta = summaries[arm]["pair_accuracy"]["mean"] - summaries["A"]["pair_accuracy"]["mean"]
        consistency_count = sum(item["margin_delta"] > 0 for item in seed_checks)
        arm_pass = (
            (mean_margin_delta >= cfg["release_gates"]["paired_margin_improvement_min"] or mean_accuracy_delta >= cfg["release_gates"]["or_pair_accuracy_improvement_min"])
            and consistency_count >= cfg["release_gates"]["winning_seed_count_min"]
            and all(item["legality_non_degradation"] and item["m1_reward_non_regression"] and item["m1_legality_non_regression"] for item in seed_checks)
            and all(r["evaluation"]["equivalence_preservation"]["preservation_rate"] == 1.0 for r in reports[arm])
            and all(r["adapter_changed"] and r["checkpoint_resume_verified"] for r in reports[arm])
        )
        gates[arm] = {
            "pass": arm_pass, "mean_margin_delta_vs_A": mean_margin_delta,
            "mean_accuracy_delta_vs_A": mean_accuracy_delta,
            "positive_margin_seed_count": consistency_count, "seed_checks": seed_checks,
        }
    any_release = gates["B"]["pass"] or gates["C"]["pass"]
    report = {
        "schema_version": "vaguehydro.preference_pilot_report.v1",
        "status": "complete",
        "decision": "PASS_ELIGIBLE_FOR_SEPARATE_FORMAL_TRAINING_PROTOCOL" if any_release else "BLOCKED_NO_FORMAL_TRAINING",
        "any_arm_passes_release_gates": any_release,
        "arm_summaries": summaries,
        "release_gates": gates,
        "seeds": cfg["seeds"],
        "arm_seed_reports": {arm: [str(run_dir / f"arm_{arm}" / f"seed_{seed}" / "ARM_SEED_REPORT.json") for seed in cfg["seeds"]] for arm in reports},
        "frozen_240_reads": 0,
        "validation_used_for_tuning": False,
        "formal_training_started": False,
    }
    write_json(run_dir / "PILOT_REPORT.json", report)
    lines = [
        "# Preference Training Pilot v1", "",
        f"- Decision: **{report['decision']}**",
        f"- Seeds: `{cfg['seeds']}`", "- Frozen-240 reads: `0`", "",
        "| Arm | Pair accuracy | Pair margin | Held-out legal | M1 Reward A | Release |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for arm in ("A", "B", "C"):
        gate = "control" if arm == "A" else str(gates[arm]["pass"])
        item = summaries[arm]
        lines.append(f"| {arm} | {item['pair_accuracy']['mean']:.6f} | {item['pair_margin']['mean']:.6f} | {item['heldout_legality']['mean']:.6f} | {item['m1_reward_a']['mean']:.6f} | {gate} |")
    (run_dir / "PILOT_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "decision": report["decision"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
