from __future__ import annotations

import argparse
import gc
import json
import time

from hydro_remote_agent.tools.vaguehydro_legality_repair_core import generate_rows, load_eval, score_rows
from hydro_remote_agent.tools.vaguehydro_preference_pilot_core import (
    ROOT,
    environment_snapshot,
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
    write_json,
)


def verify_frozen_inputs(run_dir, cfg) -> None:
    for name, expected in cfg["input_hashes"].items():
        if name == "config":
            continue
        actual = sha256_file(run_dir / name)
        if actual != expected:
            raise ValueError(f"frozen input mismatch for {name}: {actual} != {expected}")


def evaluate(model, tokenizer, run_dir, cfg, constrained):
    result = {}
    details = {}
    for split, filename in (("heldout", "heldout_eval.jsonl"), ("m1_validation", "m1_validation_eval.jsonl")):
        rows = load_eval(run_dir, filename)
        generated = generate_rows(model, tokenizer, rows, cfg, constrained)
        metrics, scored = score_rows(generated, rows, cfg)
        result[split] = metrics
        details[split] = scored
    return result, details


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--arm", choices=("A", "B", "C", "D"), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--resume-eval-only", action="store_true")
    args = parser.parse_args()
    run_dir = ROOT / args.run_dir
    cfg = load_freeze(run_dir)
    cfg["optimization"].setdefault("dpo_beta", 0.1)
    verify_frozen_inputs(run_dir, cfg)
    if args.seed not in cfg["seeds"]:
        raise ValueError(f"seed {args.seed} is not preregistered")
    preflight = json.loads((run_dir / "PREFLIGHT_REPORT.json").read_text(encoding="utf-8"))
    if preflight.get("status") != "pass" or not preflight.get("all_checks_pass"):
        raise RuntimeError("preflight did not pass; pilot is blocked")
    arm_cfg = cfg["arms"][args.arm]
    output = run_dir / f"arm_{args.arm}" / f"seed_{args.seed}"
    if output.exists() and not args.resume_eval_only:
        raise FileExistsError(f"refusing to overwrite arm/seed output: {output}")
    if args.resume_eval_only:
        if not arm_cfg["train"]:
            raise ValueError("evaluation-only resume requires a trained arm")
        if not output.is_dir():
            raise FileNotFoundError(output)
    else:
        output.mkdir(parents=True)

    import torch

    started = time.monotonic()
    set_seed(args.seed)
    torch.cuda.reset_peak_memory_stats()
    train_rows = read_jsonl(run_dir / "serialization_train.jsonl")
    max_steps = int(cfg["optimization"]["max_optimizer_steps"])
    checkpoint_step = int(cfg["optimization"]["checkpoint_step"])
    accumulation = int(cfg["optimization"]["gradient_accumulation_steps"])
    schedule = train_schedule(train_rows, args.seed, max_steps * accumulation)
    if not args.resume_eval_only:
        write_json(output / "TRAIN_SCHEDULE.json", {
            "arm": args.arm,
            "seed": args.seed,
            "optimizer_steps": max_steps if arm_cfg["train"] else 0,
            "gradient_accumulation_steps": accumulation,
            "sample_ids": [row["id"] for row in schedule] if arm_cfg["train"] else [],
        })

    initial_adapter = ROOT / cfg["initial_sft_adapter"] / "adapter_model.safetensors"
    training_logs = []
    checkpoints = []
    resume_verified = False
    if args.resume_eval_only:
        final_checkpoint = output / f"checkpoint-{max_steps}"
        state = json.loads((final_checkpoint / "training_state.json").read_text(encoding="utf-8"))
        if state.get("completed_optimizer_steps") != max_steps or state.get("seed") != args.seed:
            raise ValueError(f"checkpoint state does not match requested resume: {state}")
        model, processor, optimizer = reload_checkpoint(cfg, final_checkpoint)
        del optimizer
        checkpoints = [{
            "path": str(final_checkpoint),
            "step": max_steps,
            "adapter_sha256": sha256_file(final_checkpoint / "adapter_model.safetensors"),
            "optimizer_sha256": sha256_file(final_checkpoint / "optimizer.pt"),
            "state_sha256": sha256_file(final_checkpoint / "training_state.json"),
        }]
        final_adapter_sha = checkpoints[-1]["adapter_sha256"]
        resume_verified = True
    else:
        model, processor = load_model_and_processor(cfg, trainable=bool(arm_cfg["train"]))
    if arm_cfg["train"] and not args.resume_eval_only:
        optimizer = optimizer_for(model, cfg)
        training_logs.extend(train_segment(
            "B", model, processor.tokenizer, optimizer, schedule, cfg, {}, 0, checkpoint_step
        ))
        checkpoint = output / f"checkpoint-{checkpoint_step}"
        checkpoints.append(save_checkpoint(checkpoint, model, processor, optimizer, checkpoint_step, args.arm, args.seed))
        del model, optimizer
        gc.collect()
        torch.cuda.empty_cache()
        model, processor, optimizer = reload_checkpoint(cfg, checkpoint)
        resume_verified = True
        training_logs.extend(train_segment(
            "B", model, processor.tokenizer, optimizer, schedule, cfg, {}, checkpoint_step, max_steps
        ))
        final_checkpoint = output / f"checkpoint-{max_steps}"
        checkpoints.append(save_checkpoint(final_checkpoint, model, processor, optimizer, max_steps, args.arm, args.seed))
        final_adapter_sha = checkpoints[-1]["adapter_sha256"]
    else:
        if not args.resume_eval_only:
            final_adapter_sha = sha256_file(initial_adapter)

    write_json(output / "TRAINING_LOG.json", training_logs)
    metrics, details = evaluate(
        model, processor.tokenizer, run_dir, cfg, bool(arm_cfg["constrained_decoder"])
    )
    write_json(output / "EVALUATION_DETAILS.json", details)
    report = {
        "schema_version": "vaguehydro.legality_repair_arm_seed.v1",
        "status": "pass",
        "arm": args.arm,
        "seed": args.seed,
        "train": bool(arm_cfg["train"]),
        "constrained_decoder": bool(arm_cfg["constrained_decoder"]),
        "optimizer_steps": max_steps if arm_cfg["train"] else 0,
        "training_population": len(train_rows) if arm_cfg["train"] else 0,
        "checkpoint_resume_verified": resume_verified,
        "resumed_after_evaluation_failure": args.resume_eval_only,
        "training_logs_unavailable_due_prior_runner_write_order": args.resume_eval_only,
        "checkpoints": checkpoints,
        "training_logs": training_logs,
        "initial_adapter_sha256": sha256_file(initial_adapter),
        "final_adapter_sha256": final_adapter_sha,
        "adapter_changed": final_adapter_sha != sha256_file(initial_adapter),
        "evaluation": metrics,
        "peak_gpu_memory_gib": torch.cuda.max_memory_allocated() / 1024**3,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "environment": environment_snapshot(),
        "frozen_240_reads": 0,
        "called_real_experts": False,
        "called_verifier": False,
        "formal_training": False,
    }
    write_json(output / "ARM_SEED_REPORT.json", report)
    (output / "ARM_SEED_REPORT.md").write_text(
        f"# Arm {args.arm} / Seed {args.seed}\n\n"
        f"- Held-out strict legality: `{metrics['heldout']['strict_legality_rate']:.6f}`\n"
        f"- Held-out Reward A: `{metrics['heldout']['reward_a']['total']:.6f}`\n"
        f"- M1 strict legality: `{metrics['m1_validation']['strict_legality_rate']:.6f}`\n"
        f"- M1 Reward A: `{metrics['m1_validation']['reward_a']['total']:.6f}`\n"
        f"- Frozen-240 reads: `0`\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "pass", "arm": args.arm, "seed": args.seed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
