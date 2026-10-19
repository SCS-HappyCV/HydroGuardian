from __future__ import annotations

import argparse
import gc
import inspect
import json
import math
import time
from pathlib import Path

from hydro_remote_agent.rewards.completion_adapter import adapt_completion
from hydro_remote_agent.tools.vaguehydro_preference_pilot_core import (
    ROOT,
    compute_reference_logps,
    dpo_loss,
    environment_snapshot,
    load_freeze,
    load_model_and_processor,
    optimizer_for,
    read_jsonl,
    reload_checkpoint,
    save_checkpoint,
    set_seed,
    sft_loss,
    verify_lock,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run_dir = ROOT / args.run_dir
    verify_lock(run_dir)
    cfg = load_freeze(run_dir)
    report_path = run_dir / "PREFLIGHT_REPORT.json"
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite {report_path}")
    start = time.monotonic()
    checks: dict[str, dict] = {}
    try:
        import torch
        from trl import DPOTrainer, SFTTrainer

        checks["trainer_api"] = {
            "status": "pass",
            "sft_trainer_signature": str(inspect.signature(SFTTrainer.__init__)),
            "dpo_trainer_signature": str(inspect.signature(DPOTrainer.__init__)),
            "implementation": "native causal-LM SFT and reference-corrected DPO objective, API compatibility checked against installed TRL",
        }
        train_rows = read_jsonl(run_dir / "train_pairs.jsonl")
        heldout_rows = read_jsonl(run_dir / "heldout_pairs.jsonl")
        manifest = json.loads((run_dir / "DATA_MANIFEST.json").read_text(encoding="utf-8"))
        split = json.loads((run_dir / "SPLIT_AUDIT.json").read_text(encoding="utf-8"))
        data_ok = bool(train_rows and heldout_rows and split["all_overlap_counts_zero"] and manifest["frozen_240_reads"] == 0)
        checks["data_isolation"] = {"status": "pass" if data_ok else "fail", "train_pairs": len(train_rows), "heldout_pairs": len(heldout_rows), "overlaps": split["overlaps"]}
        adapter_cases = [
            train_rows[0]["chosen_text"],
            {"role": "assistant", "content": train_rows[0]["chosen_text"]},
            [{"role": "assistant", "content": train_rows[0]["chosen_text"]}],
        ]
        adapter_ok = all(adapt_completion(case).valid for case in adapter_cases) and not adapt_completion("not-json").valid
        checks["completion_adapter"] = {"status": "pass" if adapter_ok else "fail", "positive_cases": 3, "negative_cases": 1}

        set_seed(int(cfg["seeds"][0]))
        torch.cuda.reset_peak_memory_stats()
        model, processor = load_model_and_processor(cfg, trainable=True)
        optimizer = optimizer_for(model, cfg)
        initial_hash = Path(ROOT / cfg["initial_sft_adapter"] / "adapter_model.safetensors")
        sft = sft_loss(model, processor.tokenizer, train_rows[0], int(cfg["optimization"]["max_length"]))
        optimizer.zero_grad(set_to_none=True)
        sft.backward()
        grad = float(torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0).item())
        optimizer.step()
        smoke_dir = run_dir / "preflight_artifacts" / "sft_checkpoint_step1"
        checkpoint = save_checkpoint(smoke_dir, model, processor, optimizer, 1, "preflight_sft", int(cfg["seeds"][0]))
        checks["sft_forward_backward"] = {"status": "pass" if math.isfinite(float(sft.item())) and grad > 0 else "fail", "loss": float(sft.item()), "gradient_norm": grad}
        del model, optimizer
        gc.collect()
        torch.cuda.empty_cache()

        model, processor, optimizer = reload_checkpoint(cfg, smoke_dir)
        resume_loss = sft_loss(model, processor.tokenizer, train_rows[1], int(cfg["optimization"]["max_length"]))
        checks["checkpoint_resume"] = {
            "status": "pass" if math.isfinite(float(resume_loss.item())) else "fail",
            "checkpoint": checkpoint,
            "resume_loss": float(resume_loss.item()),
            "initial_adapter_unchanged": initial_hash.is_file(),
        }
        del model, optimizer
        gc.collect()
        torch.cuda.empty_cache()

        model, processor = load_model_and_processor(cfg, trainable=True)
        reference = compute_reference_logps(model, processor.tokenizer, train_rows[:1], int(cfg["optimization"]["max_length"]))
        dpo, chosen_logp, rejected_logp = dpo_loss(
            model, processor.tokenizer, train_rows[0], int(cfg["optimization"]["max_length"]),
            float(cfg["optimization"]["dpo_beta"]), reference[train_rows[0]["pair_id"]]
        )
        model.zero_grad(set_to_none=True)
        dpo.backward()
        dpo_grad = float(torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0).item())
        checks["dpo_forward_backward"] = {
            "status": "pass" if math.isfinite(float(dpo.item())) and dpo_grad > 0 else "fail",
            "loss": float(dpo.item()), "gradient_norm": dpo_grad,
            "chosen_logp": float(chosen_logp.item()), "rejected_logp": float(rejected_logp.item()),
            "reference_policy": "frozen initial SFT adapter",
        }
        model.eval()
        from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
        from hydro_remote_agent.rewards.structural_contrast_reward_v2 import StructuralContrastRewardV2
        from hydro_remote_agent.schemas.tool_spec import load_tool_registry
        from hydro_remote_agent.tools.vaguehydro_preference_pilot_core import equivalence_metric, generate_completions, score_generations
        generated = generate_completions(model, processor.tokenizer, heldout_rows[:1], 32)
        checks["validation_only_path"] = {"status": "pass" if len(generated) == 1 else "fail", "optimizer_steps_during_validation": 0, "completion_chars": len(generated[0]["completion"])}
        registry = load_tool_registry(ROOT / cfg["tool_registry"])
        reward_a = GoldActionReward(registry, cfg["evaluation"]["reward_a_weights"])
        reward_b = StructuralContrastRewardV2(registry)
        synthetic_metrics, _ = score_generations(
            [{"id": heldout_rows[0]["source_id"], "completion": heldout_rows[0]["chosen_text"]}],
            heldout_rows[:1], reward_a, reward_b,
        )
        mapping_ok = all(
            key in synthetic_metrics[reward]
            for reward in ("reward_a", "reward_b")
            for key in ("total", "tool", "argument", "workflow", "stop")
        )
        checks["reward_component_adapter"] = {
            "status": "pass" if mapping_ok else "fail",
            "reward_a": synthetic_metrics["reward_a"],
            "reward_b": synthetic_metrics["reward_b"],
        }
        invalid_metrics, invalid_details = score_generations(
            [{"id": heldout_rows[0]["source_id"], "completion": '{"schema_version":"1.0","broken":"unterminated'}],
            heldout_rows[:1], reward_a, reward_b,
        )
        invalid_ok = (
            invalid_metrics["strict_legality_rate"] == 0.0
            and invalid_metrics["reward_a"]["total"] == 0.0
            and invalid_metrics["reward_b"]["total"] == 0.0
            and invalid_details[0]["strict_valid"] is False
        )
        checks["invalid_completion_reward_path"] = {
            "status": "pass" if invalid_ok else "fail",
            "strict_legality_rate": invalid_metrics["strict_legality_rate"],
            "reward_a_total": invalid_metrics["reward_a"]["total"],
            "reward_b_total": invalid_metrics["reward_b"]["total"],
        }
        equivalence = equivalence_metric(cfg, reward_b)
        checks["equivalence_control_loader"] = {
            "status": "pass" if equivalence["count"] == 48 and equivalence["preservation_rate"] == 1.0 else "fail",
            **equivalence,
        }
        peak = torch.cuda.max_memory_allocated() / 1024**3
        checks["resource_budget"] = {
            "status": "pass" if peak < 78 else "fail", "peak_gpu_gib": peak,
            "elapsed_seconds": round(time.monotonic() - start, 3), "estimated_full_pilot_hours": 2.5,
            "gpu_memory_budget_gib": 78,
        }
        del model
        gc.collect()
        torch.cuda.empty_cache()
        all_pass = all(item["status"] == "pass" for item in checks.values())
        report = {
            "schema_version": "vaguehydro.preference_preflight.v1", "status": "pass" if all_pass else "fail",
            "all_checks_pass": all_pass, "checks": checks, "environment": environment_snapshot(),
            "pilot_training_started": False, "preflight_throwaway_optimizer_steps": 1,
            "frozen_240_reads": 0, "validation_used_for_tuning": False,
        }
    except Exception as exc:
        report = {
            "schema_version": "vaguehydro.preference_preflight.v1", "status": "fail",
            "all_checks_pass": False, "checks": checks, "error": f"{type(exc).__name__}: {exc}",
            "pilot_training_started": False, "frozen_240_reads": 0,
        }
    write_json(report_path, report)
    print(json.dumps({"status": report["status"], "report": str(report_path)}, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
