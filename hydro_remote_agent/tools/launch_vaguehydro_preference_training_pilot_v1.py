from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run_dir = ROOT / args.run_dir
    freeze = json.loads((run_dir / "CONFIG_FREEZE.json").read_text(encoding="utf-8"))
    preflight = json.loads((run_dir / "PREFLIGHT_REPORT.json").read_text(encoding="utf-8"))
    if preflight.get("status") != "pass" or not preflight.get("all_checks_pass"):
        raise RuntimeError("preflight is not PASS; refusing to start pilot")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    execution = []
    for arm in ("A", "B", "C"):
        for seed in freeze["seeds"]:
            output = run_dir / f"arm_{arm}" / f"seed_{seed}"
            completed_report = output / "ARM_SEED_REPORT.json"
            if completed_report.is_file():
                execution.append({"arm": arm, "seed": seed, "returncode": 0, "skipped_completed_report": True})
                continue
            if output.exists():
                raise FileExistsError(f"incomplete arm/seed output must be archived before resume: {output}")
            output.parent.mkdir(parents=True, exist_ok=True)
            stdout_path = output.parent / f"seed_{seed}.stdout.log"
            stderr_path = output.parent / f"seed_{seed}.stderr.log"
            command = [
                sys.executable,
                str(ROOT / "hydro_remote_agent/tools/run_vaguehydro_preference_training_arm_v1.py"),
                "--run-dir", args.run_dir,
                "--arm", arm,
                "--seed", str(seed),
            ]
            with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
                completed = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
            exit_path = output.parent / f"seed_{seed}.exit_code"
            exit_path.write_text(str(completed.returncode) + "\n", encoding="utf-8")
            execution.append({"arm": arm, "seed": seed, "returncode": completed.returncode, "command": command})
            (run_dir / "EXECUTION_STATUS.json").write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
            if completed.returncode != 0:
                print(json.dumps({"status": "failed", "arm": arm, "seed": seed, "returncode": completed.returncode}))
                return completed.returncode
    aggregate = subprocess.run([
        sys.executable,
        str(ROOT / "hydro_remote_agent/tools/aggregate_vaguehydro_preference_training_pilot_v1.py"),
        "--run-dir", args.run_dir,
    ], cwd=ROOT, env=env)
    print(json.dumps({"status": "complete" if aggregate.returncode == 0 else "aggregate_failed", "returncode": aggregate.returncode}))
    return aggregate.returncode


if __name__ == "__main__":
    raise SystemExit(main())
