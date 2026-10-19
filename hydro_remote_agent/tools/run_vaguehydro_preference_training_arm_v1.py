from __future__ import annotations

import argparse
import gc
import json
import time
from pathlib import Path

from hydro_remote_agent.tools.vaguehydro_preference_pilot_core import (
    ROOT,
    compute_reference_logps,
    environment_snapshot,
    evaluation_bundle,
    load_freeze,
    load_model_and_processor,
    optimizer_for,
    read_jsonl,
    reload_checkpoint,
    save_checkpoint,
    set_seed,
    sha256_file,
    train_schedule,
    train_segment,
    verify_lock,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--arm", choices=("A", "B", "C"), required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    run_dir = ROOT / args.run_dir
    verify_lock(run_dir)
    cfg = load_freeze(run_dir)
    if args.seed not in cfg["seeds"]:
        raise ValueError(f"seed {args.seed} is not preregistered")
    preflight = json.loads((run_dir / "PREFLIGHT_REPORT.json").read_text(encoding="utf-8"))
    if preflight.get("status") != "pass" or not preflight.get("all_checks_pass"):
        raise RuntimeError("preflight did not pass; training/evaluation is blocked")
    output = run_dir / f"arm_{args.arm}" / f"seed_{args.seed}"
    if output.exists():
        raise FileExistsError(f"refusing to overwrite arm/seed output: {output}")
    output.mkdir(parents=True)
    start = time.monotonic()
    set_seed(args.seed)
    import torch

    torch.cuda.reset_peak_memory_stats()
    train_rows = read_jsonl(run_dir / "train_pairs.jsonl")
    max_steps = int(cfg["optimization"]["max_optimizer_steps"])
    checkpoint_step = int(cfg["optimization"]["checkpoint_step"])
    accumulation = int(cfg["optimization"]["gradient_accumulation_steps"])
    schedule = train_schedule(train_rows, args.seed, max_steps * accumulation)
    schedule_ids = [row["pair_id"] for row in schedule]
    write_json(output / "TRAIN_SCHEDULE.json", {
        "arm": args.arm, "seed": args.seed, "optimizer_steps": 0 if args.arm == "A" else max_steps,
        "gradient_accumulation_steps": accumulation, "pair_ids": schedule_ids if args.arm != "A" else [],
    })

    model, processor = load_model_and_processor(cfg, trainable=args.arm != "A")
    initial_adapter = ROOT / cfg["initial_sft_adapter"] / "adapter_model.safetensors"
    training_logs = []
    checkpoints = []
    reference_evidence = None
    resume_verified = False
    if args.arm in {"B", "C"}:
        optimizer = optimizer_for(model, cfg)
        reference = {}
        if args.arm == "C":
            unique_schedule = {str(row["pair_id"]): row for row in schedule}
            reference = compute_reference_logps(
                model, processor.tokenizer, list(unique_schedule.values()), int(cfg["optimization"]["max_length"])
            )
            reference_evidence = {
                "policy": "frozen initial SFT adapter",
                "pair_count": len(reference),
                "sha256": __import__("hashlib").sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest(),
            }
        training_logs.extend(train_segment(
            args.arm, model, processor.tokenizer, optimizer, schedule, cfg, reference, 0, checkpoint_step
        ))
        first_checkpoint = output / f"checkpoint-{checkpoint_step}"
        checkpoints.append(save_checkpoint(first_checkpoint, model, processor, optimizer, checkpoint_step, args.arm, args.seed))
        del model, optimizer
        gc.collect()
        torch.cuda.empty_cache()
        model, processor, optimizer = reload_checkpoint(cfg, first_checkpoint)
        resume_verified = True
        training_logs.extend(train_segment(
            args.arm, model, processor.tokenizer, optimizer, schedule, cfg, reference, checkpoint_step, max_steps
        ))
        final_checkpoint = output / f"checkpoint-{max_steps}"
        checkpoints.append(save_checkpoint(final_checkpoint, model, processor, optimizer, max_steps, args.arm, args.seed))
        final_adapter_sha = checkpoints[-1]["adapter_sha256"]
        adapter_changed = final_adapter_sha != sha256_file(initial_adapter)
    else:
        final_adapter_sha = sha256_file(initial_adapter)
        adapter_changed = False

    write_json(output / "TRAINING_LOG.json", training_logs)
    metrics, raw = evaluation_bundle(model, processor, cfg, run_dir)
    write_json(output / "EVALUATION_DETAILS.json", raw)
    report = {
        "schema_version": "vaguehydro.preference_arm_seed_report.v1",
        "status": "pass",
        "arm": args.arm,
        "arm_description": {"A": "initial SFT LoRA no-training control", "B": "hard-negative SFT", "C": "reference-corrected DPO"}[args.arm],
        "seed": args.seed,
        "optimizer_steps": 0 if args.arm == "A" else max_steps,
        "gradient_accumulation_steps": accumulation,
        "training_sample_population": 0 if args.arm == "A" else len(train_rows),
        "training_schedule_micro_steps": 0 if args.arm == "A" else len(schedule),
        "initial_adapter_sha256": sha256_file(initial_adapter),
        "final_adapter_sha256": final_adapter_sha,
        "adapter_changed": adapter_changed,
        "checkpoint_resume_verified": resume_verified,
        "checkpoints": checkpoints,
        "reference_evidence": reference_evidence,
        "training_logs": training_logs,
        "evaluation": metrics,
        "peak_gpu_memory_gib": torch.cuda.max_memory_allocated() / 1024**3,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "environment": environment_snapshot(),
        "frozen_240_reads": 0,
        "validation_used_for_tuning": False,
        "formal_training": False,
    }
    write_json(output / "ARM_SEED_REPORT.json", report)
    (output / "ARM_SEED_REPORT.md").write_text(
        f"# Arm {args.arm} / Seed {args.seed}\n\n"
        f"- Status: **PASS**\n- Optimizer steps: `{report['optimizer_steps']}`\n"
        f"- Pair accuracy: `{metrics['heldout_pair_preference']['accuracy']:.6f}`\n"
        f"- Pair mean margin: `{metrics['heldout_pair_preference']['mean_margin']:.6f}`\n"
        f"- Held-out legality: `{metrics['heldout_source_generation']['strict_legality_rate']:.6f}`\n"
        f"- M1 validation Reward A: `{metrics['m1_validation_regression']['reward_a']['total']:.6f}`\n"
        f"- Adapter changed: `{adapter_changed}`\n- Frozen-240 reads: `0`\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "pass", "arm": args.arm, "seed": args.seed, "report": str(output / 'ARM_SEED_REPORT.json')}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
