from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

from hydro_remote_agent.tools.vaguehydro_preference_pilot_core import ROOT, load_freeze, write_json


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--shard", choices=("0", "1"), required=True)
    args = parser.parse_args()
    run_dir = ROOT / args.run_dir
    cfg = load_freeze(run_dir)
    seeds = [int(seed) for seed in cfg["seeds"]]
    arms = ("A", "D") if args.shard == "0" else ("B", "C")
    jobs = [(arm, seed) for arm in arms for seed in seeds]
    status_path = run_dir / f"QUEUE_STATUS_shard{args.shard}.json"
    status = {
        "shard": args.shard,
        "status": "running",
        "started_at": now(),
        "jobs": [{"arm": arm, "seed": seed, "status": "pending"} for arm, seed in jobs],
        "frozen_240_reads": 0,
        "formal_training": False,
    }
    write_json(status_path, status)
    log_dir = run_dir / "queue_logs"
    log_dir.mkdir(exist_ok=True)
    for index, (arm, seed) in enumerate(jobs):
        status["jobs"][index]["status"] = "running"
        status["jobs"][index]["started_at"] = now()
        write_json(status_path, status)
        command = [
            sys.executable,
            "-m",
            "hydro_remote_agent.tools.run_vaguehydro_legality_repair_arm_v1",
            "--run-dir",
            args.run_dir,
            "--arm",
            arm,
            "--seed",
            str(seed),
        ]
        with (log_dir / f"arm_{arm}_seed_{seed}.stdout.log").open("w", encoding="utf-8") as stdout, (
            log_dir / f"arm_{arm}_seed_{seed}.stderr.log"
        ).open("w", encoding="utf-8") as stderr:
            completed = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
        status["jobs"][index]["finished_at"] = now()
        status["jobs"][index]["exit_code"] = completed.returncode
        status["jobs"][index]["status"] = "pass" if completed.returncode == 0 else "fail"
        write_json(status_path, status)
        if completed.returncode != 0:
            status["status"] = "fail"
            status["finished_at"] = now()
            write_json(status_path, status)
            return completed.returncode
    status["status"] = "pass"
    status["finished_at"] = now()
    write_json(status_path, status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
