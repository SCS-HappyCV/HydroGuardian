from __future__ import annotations

import argparse
import json
import shutil
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
    regression = json.loads((run_dir / "DECODER_REGRESSION_INITIAL.json").read_text(encoding="utf-8"))
    if regression.get("status") != "pass" or not regression.get("all_14_without_decoder_exception"):
        raise RuntimeError("14-sample decoder regression did not pass; resume is blocked")

    seeds = [int(seed) for seed in cfg["seeds"]]
    if args.shard == "0":
        jobs = [("B", seed, False) for seed in seeds] + [("C", seed, False) for seed in seeds]
        partial = run_dir / "arm_B" / f"seed_{seeds[0]}"
        if partial.exists() and not (partial / "ARM_SEED_REPORT.json").exists():
            archive = run_dir / "failed_attempts" / f"arm_B_seed_{seeds[0]}_unicode_decoder"
            archive.parent.mkdir(exist_ok=True)
            if archive.exists():
                raise FileExistsError(archive)
            shutil.move(str(partial), str(archive))
    else:
        jobs = [("D", seeds[0], True)] + [("D", seed, False) for seed in seeds[1:]]

    status_path = run_dir / f"QUEUE_STATUS_resume_shard{args.shard}.json"
    status = {
        "status": "running",
        "shard": args.shard,
        "started_at": now(),
        "decoder_regression_pass": True,
        "jobs": [
            {"arm": arm, "seed": seed, "resume_eval_only": resume, "status": "pending"}
            for arm, seed, resume in jobs
        ],
        "frozen_240_reads": 0,
        "formal_training": False,
    }
    write_json(status_path, status)
    log_dir = run_dir / "resume_logs"
    log_dir.mkdir(exist_ok=True)
    for index, (arm, seed, resume) in enumerate(jobs):
        report = run_dir / f"arm_{arm}" / f"seed_{seed}" / "ARM_SEED_REPORT.json"
        if report.exists():
            status["jobs"][index]["status"] = "already_complete"
            write_json(status_path, status)
            continue
        status["jobs"][index].update({"status": "running", "started_at": now()})
        write_json(status_path, status)
        command = [
            sys.executable, "-m", "hydro_remote_agent.tools.run_vaguehydro_legality_repair_arm_v1",
            "--run-dir", args.run_dir, "--arm", arm, "--seed", str(seed),
        ]
        if resume:
            command.append("--resume-eval-only")
        stem = f"arm_{arm}_seed_{seed}{'_resume_eval' if resume else ''}"
        with (log_dir / f"{stem}.stdout.log").open("w", encoding="utf-8") as stdout, (
            log_dir / f"{stem}.stderr.log"
        ).open("w", encoding="utf-8") as stderr:
            completed = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
        status["jobs"][index].update({
            "status": "pass" if completed.returncode == 0 else "fail",
            "exit_code": completed.returncode,
            "finished_at": now(),
        })
        write_json(status_path, status)
        if completed.returncode != 0:
            status.update({"status": "fail", "finished_at": now()})
            write_json(status_path, status)
            return completed.returncode
    status.update({"status": "pass", "finished_at": now()})
    write_json(status_path, status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
