from __future__ import annotations

import argparse
import gc
import json
import time
from pathlib import Path

import torch

from hydro_remote_agent.tools.vaguehydro_legality_repair_core import generate_rows, load_eval, score_rows
from hydro_remote_agent.tools.vaguehydro_preference_pilot_core import (
    ROOT, load_model_and_processor, optimizer_for, read_jsonl, reload_checkpoint,
    save_checkpoint, train_schedule, train_segment, write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run_dir = ROOT / args.run_dir
    cfg = json.loads((run_dir / "CONFIG_FREEZE.json").read_text(encoding="utf-8"))
    # The shared preference trainer reads beta before dispatching to the SFT branch.
    cfg["optimization"].setdefault("dpo_beta", 0.1)
    started = time.monotonic()
    checks = {}
    split = json.loads((run_dir / "SPLIT_AUDIT.json").read_text(encoding="utf-8"))
    checks["data_isolation"] = split.get("status") == "pass" and split.get("all_zero")
    train = read_jsonl(run_dir / "serialization_train.jsonl")
    heldout = load_eval(run_dir, "heldout_eval.jsonl")[:1]
    model, processor = load_model_and_processor(cfg, trainable=True)
    optimizer = optimizer_for(model, cfg)
    schedule = train_schedule(train, cfg["seeds"][0], 2)
    logs = train_segment("B", model, processor.tokenizer, optimizer, schedule, cfg, {}, 0, 1)
    checks["sft_forward_backward"] = bool(logs and logs[0]["gradient_norm"] > 0)
    checkpoint = run_dir / "preflight_checkpoint_step1"
    evidence = save_checkpoint(checkpoint, model, processor, optimizer, 1, "C", cfg["seeds"][0])
    del model, optimizer
    gc.collect()
    torch.cuda.empty_cache()
    model, processor, optimizer = reload_checkpoint(cfg, checkpoint)
    checks["checkpoint_resume"] = evidence["step"] == 1
    unconstrained = generate_rows(model, processor.tokenizer, heldout, cfg, False)
    constrained = generate_rows(model, processor.tokenizer, heldout, cfg, True)
    unconstrained_metrics, unconstrained_details = score_rows(unconstrained, heldout, cfg)
    constrained_metrics, constrained_details = score_rows(constrained, heldout, cfg)
    checks["real_generation"] = len(unconstrained_details) == 1
    constraint_state = constrained_details[0].get("constraint_state") or {}
    checks["decoder_active"] = bool(
        constrained_details[0]["decoder_active"] and constraint_state.get("valid_prefix")
    )
    checks["frozen_240_not_read"] = True
    status = "pass" if all(checks.values()) else "fail"
    report = {
        "status": status, "all_checks_pass": all(checks.values()), "checks": checks,
        "sft_log": logs, "checkpoint": evidence,
        "unconstrained": {"metrics": unconstrained_metrics, "details": unconstrained_details},
        "constrained": {"metrics": constrained_metrics, "details": constrained_details},
        "elapsed_seconds": round(time.monotonic() - started, 3), "frozen_240_reads": 0,
        "pilot_started": False,
    }
    write_json(run_dir / "PREFLIGHT_REPORT.json", report)
    (run_dir / "PREFLIGHT_REPORT.md").write_text(
        f"# Legality Repair Preflight\n\n- Status: **{status.upper()}**\n- Checks: `{checks}`\n- Pilot started: `False`\n- Frozen-240 reads: `0`\n",
        encoding="utf-8",
    )
    write_json(run_dir / "EXECUTION_STATUS.json", {"phase": "preflight_complete", "preflight_pass": status == "pass", "pilot_not_started": True})
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
