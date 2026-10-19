from __future__ import annotations

import argparse
import json

from hydro_remote_agent.tools.vaguehydro_preference_pilot_core import ROOT, load_freeze, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run_dir = ROOT / args.run_dir
    cfg = load_freeze(run_dir)
    gate = cfg["release_gates"]
    reports = []
    missing = []
    for arm in cfg["arms"]:
        for seed in cfg["seeds"]:
            path = run_dir / f"arm_{arm}" / f"seed_{seed}" / "ARM_SEED_REPORT.json"
            if path.is_file():
                reports.append(json.loads(path.read_text(encoding="utf-8")))
            else:
                missing.append(str(path.relative_to(run_dir)))
    arm_summary = {}
    for arm in cfg["arms"]:
        rows = [row for row in reports if row["arm"] == arm]
        seed_passes = []
        for row in rows:
            heldout = row["evaluation"]["heldout"]
            m1 = row["evaluation"]["m1_validation"]
            passed = (
                heldout["strict_legality_rate"] >= gate["heldout_strict_legality_min"]
                and m1["strict_legality_rate"] >= gate["m1_strict_legality_min"]
                and heldout["reward_a"]["total"] >= gate["heldout_reward_a_min"]
                and m1["reward_a"]["total"] >= gate["m1_reward_a_min"]
            )
            seed_passes.append({"seed": row["seed"], "pass": passed, "evaluation": row["evaluation"]})
        arm_summary[arm] = {
            "completed_seeds": len(rows),
            "passing_seeds": sum(item["pass"] for item in seed_passes),
            "release_pass": len(rows) == len(cfg["seeds"]) and sum(item["pass"] for item in seed_passes) >= gate["winning_seed_count_min"],
            "seeds": seed_passes,
        }
    repair_winners = [arm for arm in ("B", "C", "D") if arm_summary[arm]["release_pass"]]
    complete = not missing
    released = complete and bool(repair_winners)
    report = {
        "schema_version": "vaguehydro.legality_repair_summary.v1",
        "status": "pass" if released else ("incomplete" if not complete else "fail"),
        "pilot_complete": complete,
        "pilot_release": released,
        "winning_repair_arms": repair_winners,
        "release_gates": gate,
        "arms": arm_summary,
        "missing_reports": missing,
        "frozen_240_reads": 0,
        "called_real_experts": False,
        "called_verifier": False,
        "formal_training_started": False,
    }
    write_json(run_dir / "PILOT_SUMMARY.json", report)
    (run_dir / "PILOT_SUMMARY.md").write_text(
        "# Legality Repair Pilot Summary\n\n"
        f"- Status: **{report['status'].upper()}**\n"
        f"- Pilot release: `{released}`\n"
        f"- Winning repair arms: `{repair_winners}`\n"
        f"- Missing reports: `{len(missing)}`\n"
        "- Formal training started: `False`\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "release": released, "winners": repair_winners}, sort_keys=True))
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
