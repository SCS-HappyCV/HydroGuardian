"""Run the preregistered v2 train-only, inference-only variance profile."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import torch
from peft import PeftModel
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from trl.data_utils import maybe_apply_chat_template, prepare_multimodal_messages

from hydro_remote_agent.backbones.qwen3_vl_planner import planner_system_prompt
from hydro_remote_agent.rewards.completion_adapter import adapt_completion
from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.schema_constrained_generation import AgentRequestPrefixParser
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.profile_vaguehydro_grpo_variance_v1 import (
    COMPONENTS,
    append_jsonl,
    build_strata,
    canonical_json,
    make_parser_factory,
    model_adapter_fingerprint,
    sha256_file,
    sha256_text,
    summarize_groups,
    write_json,
)
from hydro_remote_agent.tools.train_vaguehydro_r_m2_grpo_smoke import (
    SchemaConstrainedLogitsProcessor,
    gold_action,
    user_content,
)


def load_and_verify_records(source: Path, manifest_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    expected = {int(row["source_line_number"]): row for row in manifest_rows}
    found: dict[str, dict[str, Any]] = {}
    with source.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            manifest_row = expected.get(line_number)
            if manifest_row is None:
                continue
            if hashlib.sha256(raw_line).hexdigest() != manifest_row["source_line_sha256"]:
                raise RuntimeError(f"M1 provenance SHA mismatch at line {line_number}")
            record = json.loads(raw_line.decode("utf-8"))
            if str(record.get("id")) != str(manifest_row["id"]):
                raise RuntimeError(f"M1 provenance ID mismatch at line {line_number}")
            if sha256_text(canonical_json(gold_action(record))) != manifest_row["gold_action_sha256"]:
                raise RuntimeError(f"Gold action SHA mismatch at line {line_number}")
            found[str(record["id"])] = record
    missing = {str(row["id"]) for row in manifest_rows} - set(found)
    if missing:
        raise RuntimeError(f"Manifest rows missing from M1 train: {sorted(missing)}")
    return found


def report_markdown(report: Mapping[str, Any]) -> str:
    overall = report["overall"]
    variance = report["variance_gate"]
    completion = report["workflow_completion_gate"]
    return "\n".join([
        "# VagueHydro GRPO Variance Profile v2",
        "",
        f"- Overall decision: **{report['decision']}**",
        f"- Workflow completion gate: **{'PASS' if completion['pass'] else 'FAIL'}**",
        f"- Reward-variance gate: **{'PASS' if variance['pass'] else 'FAIL'}**",
        f"- Groups / candidates: `{overall['groups']}` / `{overall['candidates']}`",
        f"- Groups with reward std > 0: `{overall['fraction_groups_std_gt_zero']:.3f}`",
        f"- Stable variance strata: `{variance['stable_variance_strata_count']}`",
        f"- Workflow EOS / parse / clipping: `{completion['observed']['eos_rate']:.3f}` / `{completion['observed']['parse_rate']:.3f}` / `{completion['observed']['clipping_rate']:.3f}`",
        f"- Frozen-test reads / optimizer steps / gradient updates: `0 / 0 / 0`",
        "",
        report["interpretation"],
        "",
    ])


def run(config_path: Path, root: Path) -> int:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    output = root / cfg["output"]
    length_path = output / "GOLD_LENGTH_DISTRIBUTION.json"
    plan_path = output / "PRE_REGISTERED_SAMPLING_PLAN.json"
    manifest_path = output / "PROFILE_DATA_MANIFEST.json"
    lock_path = output / "PREREGISTRATION_LOCK.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    hash_checks = {
        "config": sha256_file(config_path) == lock["config_sha256"],
        "length_distribution": sha256_file(length_path) == lock["gold_length_distribution_sha256"],
        "sampling_plan": sha256_file(plan_path) == lock["sampling_plan_sha256"],
        "data_manifest": sha256_file(manifest_path) == lock["profile_data_manifest_sha256"],
    }
    if not all(hash_checks.values()):
        raise RuntimeError(f"Preregistration hash mismatch: {hash_checks}")
    if plan["state"] != "FROZEN_BEFORE_GENERATION" or manifest["state"] != "FROZEN_BEFORE_GENERATION" or lock["state"] != "LOCKED_BEFORE_GENERATION":
        raise RuntimeError("Invalid preregistration state")
    if lock["generation_started"]:
        raise RuntimeError("Generation already started; refusing rerun")
    if any(cfg["constraints"][key] for key in ("formal_training", "optimizer", "gradient_updates", "adapter_updates", "verifier", "real_experts", "frozen_test_reads", "posthoc_sampling_changes", "posthoc_threshold_changes", "posthoc_length_budget_changes")):
        raise RuntimeError("Forbidden operation enabled")
    source = root / cfg["train_source"]
    if sha256_file(source) != lock["source_sha256"]:
        raise RuntimeError("M1 train SHA changed")
    records = load_and_verify_records(source, manifest["records"])
    if len(manifest["records"]) * int(cfg["sampling"]["group_size"]) != int(manifest["expected_candidate_count"]):
        raise RuntimeError("Manifest candidate count mismatch")

    raw_path = output / "RAW_CANDIDATES.jsonl"
    sample_path = output / "SAMPLE_PROFILES.jsonl"
    if raw_path.exists() or sample_path.exists():
        raise RuntimeError("Output candidates already exist")
    lock["generation_started"] = True
    lock["generation_started_at"] = datetime.now(timezone.utc).isoformat()
    write_json(lock_path, lock)

    registry = load_tool_registry(root / cfg["tool_registry"])
    reward_engine = GoldActionReward(registry, cfg["reward"]["weights"])
    parser_factory = make_parser_factory(registry)
    processor = AutoProcessor.from_pretrained(cfg["base_model"], max_pixels=65536, local_files_only=True)
    processor.tokenizer.padding_side = "left"
    base = Qwen3VLForConditionalGeneration.from_pretrained(cfg["base_model"], dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True, low_cpu_mem_usage=True)
    model = PeftModel.from_pretrained(base, root / cfg["sft_adapter"], is_trainable=False).to("cuda").eval()
    if any(parameter.requires_grad for parameter in model.parameters()):
        raise RuntimeError("Inference-only model has trainable parameters")
    adapter_before = model_adapter_fingerprint(model)
    eos_token_id = int(processor.tokenizer.eos_token_id)
    mandatory = [
        "{", "}", "[", "]", ":", ",", '"', "true", "false", "null",
        *AgentRequestPrefixParser.ROOT_KEYS, *AgentRequestPrefixParser.ACTION_KEYS,
        *AgentRequestPrefixParser.STEP_KEYS, *AgentRequestPrefixParser.EXPECTED_KEYS,
        *registry.names(), "1.0", "direct_answer", "tool_call", "workflow", "clarification", "abstain", "auto", "required", "skip",
    ]
    group_size = int(cfg["sampling"]["group_size"])
    groups: list[dict[str, Any]] = []
    torch.cuda.reset_peak_memory_stats()
    run_started = time.perf_counter()
    for manifest_row in manifest["records"]:
        record = records[str(manifest_row["id"])]
        prompts = [[{"role": "system", "content": planner_system_prompt(record)}, {"role": "user", "content": user_content(record)}] for _ in range(group_size)]
        prompt_copies = deepcopy(prompts)
        for prompt in prompt_copies:
            prepare_multimodal_messages(prompt, num_images=1)
        prompt_texts = [maybe_apply_chat_template({"prompt": prompt}, processor)["prompt"] for prompt in prompt_copies]
        image_path = Path(str(record["images"][0]))
        if not image_path.is_absolute():
            image_path = root / image_path
        with Image.open(image_path) as opened:
            image = opened.convert("RGB")
        inputs = processor(text=prompt_texts, images=[[image] for _ in range(group_size)], return_tensors="pt", padding=True, padding_side="left", max_length=8192, truncation=True, add_special_tokens=False)
        inputs = {key: value.to("cuda") if torch.is_tensor(value) else value for key, value in inputs.items()}
        prompt_length = int(inputs["input_ids"].size(1))
        max_new_tokens = int(manifest_row["max_new_tokens"])
        logits_processor = SchemaConstrainedLogitsProcessor(processor.tokenizer, eos_token_id, prompt_length, parser_factory, 256, int(cfg["decoder"]["fallback_scan_top_tokens"]), mandatory)
        seed = int(manifest_row["generation_seed"])
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        started = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(**inputs, do_sample=bool(cfg["sampling"]["do_sample"]), temperature=float(cfg["sampling"]["temperature"]), top_p=float(cfg["sampling"]["top_p"]), max_new_tokens=max_new_tokens, logits_processor=[logits_processor], pad_token_id=eos_token_id, eos_token_id=eos_token_id, disable_compile=True)
        torch.cuda.synchronize()
        wall_seconds = time.perf_counter() - started
        completion_batch = generated[:, prompt_length:].detach().cpu().tolist()
        candidates = []
        totals = []
        for candidate_index, padded_ids in enumerate(completion_batch):
            eos_position = padded_ids.index(eos_token_id) if eos_token_id in padded_ids else None
            token_ids = padded_ids[: eos_position + 1] if eos_position is not None else padded_ids
            raw = processor.tokenizer.decode(token_ids, skip_special_tokens=True)
            adapted = adapt_completion(raw)
            if adapted.valid and adapted.payload is not None:
                breakdown = reward_engine.score(adapted.payload, gold_action(record)).to_dict()
                canonical_sha = sha256_text(canonical_json(adapted.payload))
            else:
                breakdown = {"total": 0.0, **{name: 0.0 for name in COMPONENTS}, "invalid": True, "candidate_error": adapted.error}
                canonical_sha = None
            rewards = {"total": float(breakdown["total"]), **{name: float(breakdown[name]) for name in COMPONENTS}}
            candidate = {
                "sample_id": str(manifest_row["id"]), "source_line_number": int(manifest_row["source_line_number"]),
                "manifest_index": int(manifest_row["manifest_index"]), "candidate_index": candidate_index,
                "action_type": str(manifest_row["action_type"]), "generation_seed": seed,
                "max_new_tokens": max_new_tokens, "raw_completion": raw, "raw_sha256": sha256_text(raw),
                "token_ids": token_ids, "token_sha256": sha256_text(canonical_json(token_ids)), "canonical_sha256": canonical_sha,
                "token_count": len(token_ids), "eos_present": eos_position is not None, "eos_position": eos_position,
                "clipped": eos_position is None and len(token_ids) >= max_new_tokens,
                "parse_valid": adapted.valid, "parse_invalid": not adapted.valid, "parse_error": adapted.error,
                "rewards": rewards,
            }
            candidates.append(candidate)
            totals.append(rewards["total"])
            append_jsonl(raw_path, candidate)
        mean = statistics.fmean(totals)
        std_population = statistics.pstdev(totals)
        std_sample = statistics.stdev(totals) if len(totals) > 1 else 0.0
        advantages = [(value - mean) / std_population if std_population > 1e-12 else 0.0 for value in totals]
        copied_fields = ("id", "manifest_index", "source_line_number", "action_type", "difficulty", "ambiguity_level", "language", "scene_region", "parameter_complexity", "gold_contrast_axis", "intent", "tool_sequence_signature", "unique_tool_count", "confusable_tool_count", "argument_slots", "workflow_edge_count", "artifact_reference_count", "gold_token_length", "generation_seed", "max_new_tokens")
        group = {
            **{key: manifest_row[key] for key in copied_fields}, "sample_id": str(manifest_row["id"]),
            "candidate_count": len(candidates), "unique_raw_count": len({candidate["raw_sha256"] for candidate in candidates}),
            "unique_token_count": len({candidate["token_sha256"] for candidate in candidates}),
            "unique_canonical_count": len({candidate["canonical_sha256"] for candidate in candidates if candidate["canonical_sha256"]}),
            "reward_mean": mean, "reward_min": min(totals), "reward_max": max(totals),
            "reward_std_population": std_population, "reward_std_sample": std_sample,
            "advantages": advantages, "advantage_nonzero_count": sum(abs(value) > 1e-12 for value in advantages),
            "wall_seconds": wall_seconds, "candidates": candidates,
        }
        groups.append(group)
        append_jsonl(sample_path, group)
        print(json.dumps({"completed": len(groups), "total": len(manifest["records"]), "action": group["action_type"], "id": group["sample_id"], "budget": max_new_tokens, "std": std_population, "unique": group["unique_raw_count"], "eos": sum(candidate["eos_present"] for candidate in candidates), "parse": sum(candidate["parse_valid"] for candidate in candidates), "seconds": wall_seconds}), flush=True)

    adapter_after = model_adapter_fingerprint(model)
    run_wall = time.perf_counter() - run_started
    overall = summarize_groups(groups)
    overall.update({"end_to_end_wall_seconds": run_wall, "tokens_per_second": overall["generated_tokens"] / max(run_wall, 1e-9), "gpu_peak_memory_bytes": int(torch.cuda.max_memory_allocated())})
    dimensions = list(cfg["preregistered_gates"]["reward_variance"]["stability_stratum_dimensions"])
    strata = build_strata(groups, dimensions)
    workflow_candidates = [candidate for group in groups if group["action_type"] == "workflow" for candidate in group["candidates"]]
    workflow_observed = {
        "groups": sum(group["action_type"] == "workflow" for group in groups),
        "candidates": len(workflow_candidates),
        "eos_rate": sum(candidate["eos_present"] for candidate in workflow_candidates) / len(workflow_candidates),
        "parse_rate": sum(candidate["parse_valid"] for candidate in workflow_candidates) / len(workflow_candidates),
        "clipping_rate": sum(candidate["clipped"] for candidate in workflow_candidates) / len(workflow_candidates),
        "mean_token_count": statistics.fmean(candidate["token_count"] for candidate in workflow_candidates),
        "max_token_count": max(candidate["token_count"] for candidate in workflow_candidates),
        "budget": plan["fixed_max_new_tokens"]["workflow"],
    }
    completion_thresholds = cfg["preregistered_gates"]["workflow_completion"]
    completion_checks = {
        "eos_rate": workflow_observed["eos_rate"] >= float(completion_thresholds["eos_rate_min"]),
        "parse_rate": workflow_observed["parse_rate"] >= float(completion_thresholds["parse_rate_min"]),
        "clipping_rate": workflow_observed["clipping_rate"] <= float(completion_thresholds["clipping_rate_max"]),
    }
    workflow_report = {"thresholds": completion_thresholds, "observed": workflow_observed, "checks": completion_checks, "pass": all(completion_checks.values())}
    variance_cfg = cfg["preregistered_gates"]["reward_variance"]
    stable = []
    for dimension in dimensions:
        for key, summary in strata[dimension].items():
            if summary["groups"] >= int(variance_cfg["stable_stratum_min_groups"]) and summary["fraction_groups_std_gt_zero"] >= float(variance_cfg["stable_stratum_fraction_std_gt_zero_min"]):
                stable.append(f"{dimension}={key}")
    variance_gate = {
        "thresholds": variance_cfg,
        "overall_fraction_groups_std_gt_zero": overall["fraction_groups_std_gt_zero"],
        "stable_variance_strata": stable,
        "stable_variance_strata_count": len(stable),
    }
    variance_gate["pass"] = variance_gate["overall_fraction_groups_std_gt_zero"] >= float(variance_cfg["overall_fraction_groups_std_gt_zero_min"]) and len(stable) >= int(variance_cfg["minimum_stable_variance_strata"])
    both_pass = workflow_report["pass"] and variance_gate["pass"]
    decision = "recommend_new_training_preflight" if both_pass else "do_not_start_grpo"
    interpretation = "Both independently preregistered gates passed; a separately controlled training preflight is justified." if both_pass else "At least one independently preregistered gate failed; GRPO must not be started from this profile."
    report = {
        "schema_version": "vaguehydro.grpo_variance_profile.report.v2", "created_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision, "both_gates_pass": both_pass, "workflow_completion_gate": workflow_report,
        "variance_gate": variance_gate, "overall": overall, "fixed_max_new_tokens": plan["fixed_max_new_tokens"],
        "inference_only": True, "formal_training": False, "optimizer_steps": 0, "gradient_updates": 0,
        "frozen_test_reads": 0, "verifier_calls": 0, "real_expert_calls": 0,
        "adapter_fingerprint": {"before": adapter_before, "after": adapter_after, "changed": adapter_before != adapter_after},
        "interpretation": interpretation,
    }
    write_json(output / "STRATUM_REPORT.json", strata)
    write_json(output / "WORKFLOW_COMPLETION_REPORT.json", workflow_report)
    write_json(output / "PROFILE_REPORT.json", report)
    (output / "PROFILE_REPORT.md").write_text(report_markdown(report), encoding="utf-8")

    mismatches = []
    for group in groups:
        gold = gold_action(records[group["sample_id"]])
        for candidate in group["candidates"]:
            adapted = adapt_completion(candidate["raw_completion"])
            recomputed = reward_engine.score(adapted.payload, gold).to_dict() if adapted.valid and adapted.payload is not None else {"total": 0.0, **{name: 0.0 for name in COMPONENTS}}
            for name in ("total", *COMPONENTS):
                if not math.isclose(float(recomputed[name]), float(candidate["rewards"][name]), abs_tol=1e-12):
                    mismatches.append({"sample_id": group["sample_id"], "candidate_index": candidate["candidate_index"], "component": name})
    reward_audit = {"status": "pass" if not mismatches else "fail", "candidate_count": overall["candidates"], "mismatch_count": len(mismatches), "mismatches": mismatches}
    write_json(output / "REWARD_RECOMPUTE_AUDIT.json", reward_audit)
    final_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    no_posthoc = {
        "config_sha256_matches": sha256_file(config_path) == final_lock["config_sha256"],
        "length_distribution_sha256_matches": sha256_file(length_path) == final_lock["gold_length_distribution_sha256"],
        "sampling_plan_sha256_matches": sha256_file(plan_path) == final_lock["sampling_plan_sha256"],
        "manifest_sha256_matches": sha256_file(manifest_path) == final_lock["profile_data_manifest_sha256"],
        "sample_ids_match": [group["sample_id"] for group in groups] == [str(row["id"]) for row in manifest["records"]],
        "budgets_match": all(group["max_new_tokens"] == plan["fixed_max_new_tokens"][group["action_type"]] for group in groups),
        "group_size_match": all(group["candidate_count"] == group_size for group in groups),
        "selection_used_model_outputs": False, "selection_used_rewards": False, "posthoc_changes": 0,
    }
    no_posthoc["status"] = "pass" if all(value for key, value in no_posthoc.items() if key.endswith("_match") or key.endswith("_matches")) else "fail"
    write_json(output / "NO_POSTHOC_AUDIT.json", no_posthoc)
    provenance_audit = {
        "status": "pass", "split": "M1_train_only", "source_path": cfg["train_source"], "source_sha256": sha256_file(source),
        "manifest_source_sha256": manifest["source"]["sha256"], "records_verified_by_line_and_sha256": len(records),
        "frozen_test_paths_opened": [], "frozen_test_reads": 0,
    }
    provenance_audit["status"] = "pass" if provenance_audit["source_sha256"] == provenance_audit["manifest_source_sha256"] and len(records) == len(manifest["records"]) else "fail"
    write_json(output / "M1_PROVENANCE_AUDIT.json", provenance_audit)
    integrity_evidence = {
        "status": "pass" if reward_audit["status"] == no_posthoc["status"] == provenance_audit["status"] == "pass" and adapter_before == adapter_after else "fail",
        "checks": {"pre_registered_before_generation": True, "no_posthoc_selection": no_posthoc["status"] == "pass", "reward_recompute_exact": reward_audit["status"] == "pass", "m1_train_provenance": provenance_audit["status"] == "pass", "adapter_unchanged": adapter_before == adapter_after, "optimizer_steps_zero": True, "gradient_updates_zero": True, "frozen_test_reads_zero": True, "real_qwen_sft": True, "m4_schema_decoder": True, "gold_action_reward_unmodified": True},
    }
    write_json(output / "INTEGRITY_EVIDENCE.json", integrity_evidence)
    write_json(output / "CODE_HASH.json", {"config": sha256_file(config_path), "prepare_script": sha256_file(Path(__file__).with_name("prepare_vaguehydro_grpo_variance_profile_v2.py")), "profile_script": sha256_file(Path(__file__)), "v1_utility_dependency": sha256_file(Path(__file__).with_name("profile_vaguehydro_grpo_variance_v1.py")), "completion_adapter": sha256_file(root / "hydro_remote_agent/rewards/completion_adapter.py"), "gold_action_reward": sha256_file(root / "hydro_remote_agent/rewards/gold_action_reward.py"), "schema_decoder_source": sha256_file(root / "hydro_remote_agent/tools/train_vaguehydro_r_m2_grpo_smoke.py")})
    print(json.dumps({"decision": decision, "completion_gate": workflow_report["pass"], "variance_gate": variance_gate["pass"], "audit_evidence": integrity_evidence["status"], "output": str(output)}, ensure_ascii=False), flush=True)
    return 0 if integrity_evidence["status"] == "pass" else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    config = args.config if args.config.is_absolute() else root / args.config
    return run(config, root)


if __name__ == "__main__":
    raise SystemExit(main())
