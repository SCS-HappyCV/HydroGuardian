"""Paired inference-only profile of frozen GoldActionReward A and structural reward B."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
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
from hydro_remote_agent.rewards.structural_contrast_reward import COMPONENTS as B_COMPONENTS, StructuralContrastReward
from hydro_remote_agent.schema_constrained_generation import AgentRequestPrefixParser
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.profile_vaguehydro_grpo_variance_v1 import (
    COMPONENTS as A_COMPONENTS,
    append_jsonl,
    canonical_json,
    make_parser_factory,
    model_adapter_fingerprint,
    sha256_file,
    sha256_text,
    write_json,
)
from hydro_remote_agent.tools.profile_vaguehydro_grpo_variance_v2 import load_and_verify_records
from hydro_remote_agent.tools.train_vaguehydro_r_m2_grpo_smoke import SchemaConstrainedLogitsProcessor, gold_action, user_content


def summarize(groups: list[dict[str, Any]], reward_key: str) -> dict[str, Any]:
    eps = 1e-12
    candidates = [candidate for group in groups for candidate in group["candidates"]]
    valid_candidates = [candidate for candidate in candidates if candidate["parse_valid"]]
    return {
        "groups": len(groups), "candidates": len(candidates), "valid_candidates": len(valid_candidates),
        "fraction_groups_std_gt_zero": sum(group[reward_key]["std_population"] > eps for group in groups) / max(1, len(groups)),
        "zero_variance_rate": sum(group[reward_key]["std_population"] <= eps for group in groups) / max(1, len(groups)),
        "valid_nonzero_advantage_ratio": sum(group[reward_key]["valid_nonzero_advantage_count"] for group in groups) / max(1, len(valid_candidates)),
        "mean_reward": statistics.fmean(candidate[reward_key]["total"] for candidate in candidates) if candidates else 0.0,
        "saturated_candidate_rate": sum(candidate[reward_key]["total"] >= 1.0 - eps for candidate in candidates) / max(1, len(candidates)),
        "saturated_group_rate": sum(group[reward_key]["minimum"] >= 1.0 - eps and group[reward_key]["maximum"] >= 1.0 - eps for group in groups) / max(1, len(groups)),
        "mean_group_std": statistics.fmean(group[reward_key]["std_population"] for group in groups) if groups else 0.0,
    }


def stratify(groups: list[dict[str, Any]], reward_key: str) -> dict[str, Any]:
    output = {}
    for dimension in ("action_type", "difficulty", "action_relative_complexity_band", "tool_sequence_signature"):
        cells: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for group in groups:
            cells[str(group[dimension])].append(group)
        output[dimension] = {key: summarize(value, reward_key) for key, value in sorted(cells.items())}
    return output


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def paired_bootstrap(group_differences: list[float], seed: int, replicates: int) -> dict[str, Any]:
    rng = random.Random(seed)
    count = len(group_differences)
    means = []
    for _ in range(replicates):
        means.append(sum(group_differences[rng.randrange(count)] for _ in range(count)) / count)
    return {
        "method": "paired group bootstrap with replacement",
        "seed": seed,
        "replicates": replicates,
        "observed_mean_uplift": statistics.fmean(group_differences),
        "ci95_lower": percentile(means, 0.025),
        "ci95_upper": percentile(means, 0.975),
    }


def group_reward_summary(values: list[float], valid_flags: list[bool]) -> dict[str, Any]:
    mean = statistics.fmean(values)
    std = statistics.pstdev(values)
    advantages = [(value - mean) / std if std > 1e-12 else 0.0 for value in values]
    return {
        "mean": mean, "minimum": min(values), "maximum": max(values), "std_population": std,
        "std_sample": statistics.stdev(values) if len(values) > 1 else 0.0, "advantages": advantages,
        "valid_nonzero_advantage_count": sum(valid and abs(advantage) > 1e-12 for valid, advantage in zip(valid_flags, advantages)),
    }


def markdown_report(report: Mapping[str, Any]) -> str:
    a = report["reward_a_overall"]
    b = report["reward_b_overall"]
    completion = report["workflow_completion_gate"]
    return "\n".join([
        "# VagueHydro Reward Design v1",
        "",
        f"- Decision: **{report['decision']}**",
        f"- Baseline reproduction: **{'PASS' if report['baseline_reproduction_gate']['pass'] else 'FAIL'}**",
        f"- Reward B variance gate: **{'PASS' if report['reward_b_variance_gate']['pass'] else 'FAIL'}**",
        f"- Advantage uplift gate: **{'PASS' if report['advantage_uplift_gate']['pass'] else 'FAIL'}**",
        f"- Workflow completion gate: **{'PASS' if completion['pass'] else 'FAIL'}**",
        f"- A / B non-zero-std groups: `{a['fraction_groups_std_gt_zero']:.3f}` / `{b['fraction_groups_std_gt_zero']:.3f}`",
        f"- A / B valid non-zero-advantage ratio: `{a['valid_nonzero_advantage_ratio']:.3f}` / `{b['valid_nonzero_advantage_ratio']:.3f}`",
        f"- Workflow EOS / parse / clipping: `{completion['observed']['eos_rate']:.3f}` / `{completion['observed']['parse_rate']:.3f}` / `{completion['observed']['clipping_rate']:.3f}`",
        "",
        report["interpretation"],
        "",
    ])


def run(config_path: Path, root: Path) -> int:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    output = root / cfg["output"]
    paths = {
        "plan": output / "PRE_REGISTERED_PLAN.json", "spec_a": output / "REWARD_SPEC_A.json",
        "spec_b": output / "REWARD_SPEC_B.json", "manifest": output / "DATA_MANIFEST.json",
        "lock": output / "PREREGISTRATION_LOCK.json", "unit": output / "UNIT_TEST_REPORT.json",
    }
    plan = json.loads(paths["plan"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    lock = json.loads(paths["lock"].read_text(encoding="utf-8"))
    hash_checks = {
        "config": sha256_file(config_path) == lock["config_sha256"], "plan": sha256_file(paths["plan"]) == lock["pre_registered_plan_sha256"],
        "spec_a": sha256_file(paths["spec_a"]) == lock["reward_spec_a_sha256"], "spec_b": sha256_file(paths["spec_b"]) == lock["reward_spec_b_sha256"],
        "manifest": sha256_file(paths["manifest"]) == lock["data_manifest_sha256"],
        "reward_b_code": sha256_file(root / "hydro_remote_agent/rewards/structural_contrast_reward.py") == lock["reward_b_code_sha256"],
        "reward_b_test": sha256_file(root / "hydro_remote_agent/tests/test_structural_contrast_reward_unittest.py") == lock["reward_b_test_sha256"],
        "unit_report": sha256_file(paths["unit"]) == lock["unit_test_report_sha256"],
    }
    if not all(hash_checks.values()) or lock["generation_started"] or json.loads(paths["unit"].read_text(encoding="utf-8"))["status"] != "pass":
        raise RuntimeError(f"Preregistration/unit-test check failed: {hash_checks}")
    source = root / cfg["train_source"]
    if sha256_file(source) != lock["source_sha256"]:
        raise RuntimeError("M1 train source changed")
    forbidden = ("formal_grpo", "optimizer", "gradient_updates", "adapter_updates", "frozen_test_reads", "verifier", "real_experts", "posthoc_weight_changes", "posthoc_sample_deletion", "posthoc_threshold_changes")
    if any(cfg["constraints"][key] for key in forbidden):
        raise RuntimeError("A forbidden operation is enabled")
    records = load_and_verify_records(source, manifest["records"])
    raw_path = output / "RAW_CANDIDATES.jsonl"
    group_path = output / "GROUP_PROFILES.jsonl"
    if raw_path.exists() or group_path.exists():
        raise RuntimeError("Generation output already exists")
    lock["generation_started"] = True
    lock["generation_started_at"] = datetime.now(timezone.utc).isoformat()
    write_json(paths["lock"], lock)

    registry = load_tool_registry(root / cfg["tool_registry"])
    reward_a = GoldActionReward(registry, cfg["reward_a"]["weights"])
    reward_b = StructuralContrastReward(registry)
    parser_factory = make_parser_factory(registry)
    processor = AutoProcessor.from_pretrained(cfg["base_model"], max_pixels=65536, local_files_only=True)
    processor.tokenizer.padding_side = "left"
    base = Qwen3VLForConditionalGeneration.from_pretrained(cfg["base_model"], dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True, low_cpu_mem_usage=True)
    model = PeftModel.from_pretrained(base, root / cfg["sft_adapter"], is_trainable=False).to("cuda").eval()
    if any(parameter.requires_grad for parameter in model.parameters()):
        raise RuntimeError("Inference model has trainable parameters")
    adapter_before = model_adapter_fingerprint(model)
    eos_token_id = int(processor.tokenizer.eos_token_id)
    mandatory = ["{", "}", "[", "]", ":", ",", '"', "true", "false", "null", *AgentRequestPrefixParser.ROOT_KEYS, *AgentRequestPrefixParser.ACTION_KEYS, *AgentRequestPrefixParser.STEP_KEYS, *AgentRequestPrefixParser.EXPECTED_KEYS, *registry.names(), "1.0", "direct_answer", "tool_call", "workflow", "clarification", "abstain", "auto", "required", "skip"]
    group_size = int(cfg["sampling"]["group_size"])
    groups: list[dict[str, Any]] = []
    run_started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    for manifest_row in manifest["records"]:
        record = records[str(manifest_row["id"])]
        prompts = [[{"role": "system", "content": planner_system_prompt(record)}, {"role": "user", "content": user_content(record)}] for _ in range(group_size)]
        prompt_copies = deepcopy(prompts)
        for prompt in prompt_copies:
            prepare_multimodal_messages(prompt, num_images=1)
        prompt_texts = [maybe_apply_chat_template({"prompt": prompt}, processor)["prompt"] for prompt in prompt_copies]
        image_path = Path(str(record["images"][0])); image_path = image_path if image_path.is_absolute() else root / image_path
        with Image.open(image_path) as opened:
            image = opened.convert("RGB")
        inputs = processor(text=prompt_texts, images=[[image] for _ in range(group_size)], return_tensors="pt", padding=True, padding_side="left", max_length=8192, truncation=True, add_special_tokens=False)
        inputs = {key: value.to("cuda") if torch.is_tensor(value) else value for key, value in inputs.items()}
        prompt_length = int(inputs["input_ids"].size(1)); max_new_tokens = int(manifest_row["max_new_tokens"])
        logits_processor = SchemaConstrainedLogitsProcessor(processor.tokenizer, eos_token_id, prompt_length, parser_factory, 256, int(cfg["decoder"]["fallback_scan_top_tokens"]), mandatory)
        seed = int(manifest_row["generation_seed"]); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
        started = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(**inputs, do_sample=bool(cfg["sampling"]["do_sample"]), temperature=float(cfg["sampling"]["temperature"]), top_p=float(cfg["sampling"]["top_p"]), max_new_tokens=max_new_tokens, logits_processor=[logits_processor], pad_token_id=eos_token_id, eos_token_id=eos_token_id, disable_compile=True)
        torch.cuda.synchronize(); wall_seconds = time.perf_counter() - started
        batch = generated[:, prompt_length:].detach().cpu().tolist(); candidates = []; a_values = []; b_values = []; valid_flags = []
        gold = gold_action(record)
        for candidate_index, padded_ids in enumerate(batch):
            eos_position = padded_ids.index(eos_token_id) if eos_token_id in padded_ids else None
            token_ids = padded_ids[: eos_position + 1] if eos_position is not None else padded_ids
            raw = processor.tokenizer.decode(token_ids, skip_special_tokens=True); adapted = adapt_completion(raw)
            if adapted.valid and adapted.payload is not None:
                a_breakdown = reward_a.score(adapted.payload, gold).to_dict(); b_breakdown = reward_b.score(adapted.payload, gold).to_dict()
            else:
                a_breakdown = {"total": 0.0, **{name: 0.0 for name in A_COMPONENTS}, "invalid": True, "candidate_error": adapted.error}
                b_breakdown = {"total": 0.0, **{name: 0.0 for name in B_COMPONENTS}, "invalid": True, "candidate_error": adapted.error}
            a_payload = {"total": float(a_breakdown["total"]), **{name: float(a_breakdown[name]) for name in A_COMPONENTS}}
            b_payload = {"total": float(b_breakdown["total"]), **{name: float(b_breakdown[name]) for name in B_COMPONENTS}}
            candidate = {
                "sample_id": str(manifest_row["id"]), "manifest_index": int(manifest_row["manifest_index"]), "candidate_index": candidate_index,
                "source_line_number": int(manifest_row["source_line_number"]), "action_type": manifest_row["action_type"], "generation_seed": seed,
                "max_new_tokens": max_new_tokens, "raw_completion": raw, "raw_sha256": sha256_text(raw), "token_ids": token_ids,
                "token_sha256": sha256_text(canonical_json(token_ids)), "token_count": len(token_ids), "eos_present": eos_position is not None,
                "eos_position": eos_position, "clipped": eos_position is None and len(token_ids) >= max_new_tokens,
                "parse_valid": adapted.valid, "parse_invalid": not adapted.valid, "parse_error": adapted.error,
                "reward_a_original": a_payload, "reward_b_structural": b_payload,
            }
            candidates.append(candidate); a_values.append(a_payload["total"]); b_values.append(b_payload["total"]); valid_flags.append(adapted.valid)
            append_jsonl(raw_path, candidate)
        copied = ("id", "manifest_index", "source_line_number", "action_type", "difficulty", "ambiguity_level", "language", "scene_region", "intent", "tool_sequence_signature", "unique_tool_count", "step_count", "argument_slots", "action_relative_complexity_band", "edge_count", "artifact_reference_count", "generation_seed", "max_new_tokens")
        group = {**{key: manifest_row[key] for key in copied}, "sample_id": str(manifest_row["id"]), "candidate_count": len(candidates), "unique_raw_count": len({candidate["raw_sha256"] for candidate in candidates}), "wall_seconds": wall_seconds, "reward_a_original": group_reward_summary(a_values, valid_flags), "reward_b_structural": group_reward_summary(b_values, valid_flags), "candidates": candidates}
        groups.append(group); append_jsonl(group_path, group)
        print(json.dumps({"completed": len(groups), "total": len(manifest["records"]), "action": group["action_type"], "id": group["sample_id"], "std_a": group["reward_a_original"]["std_population"], "std_b": group["reward_b_structural"]["std_population"], "eos": sum(c["eos_present"] for c in candidates), "parse": sum(c["parse_valid"] for c in candidates), "seconds": wall_seconds}), flush=True)

    adapter_after = model_adapter_fingerprint(model); run_wall = time.perf_counter() - run_started
    a_overall = summarize(groups, "reward_a_original"); b_overall = summarize(groups, "reward_b_structural")
    a_strata = stratify(groups, "reward_a_original"); b_strata = stratify(groups, "reward_b_structural")
    workflow_candidates = [candidate for group in groups if group["action_type"] == "workflow" for candidate in group["candidates"]]
    completion_observed = {"candidates": len(workflow_candidates), "eos_rate": sum(c["eos_present"] for c in workflow_candidates) / len(workflow_candidates), "parse_rate": sum(c["parse_valid"] for c in workflow_candidates) / len(workflow_candidates), "clipping_rate": sum(c["clipped"] for c in workflow_candidates) / len(workflow_candidates)}
    completion_cfg = cfg["preregistered_gates"]["workflow_completion"]
    completion_checks = {"eos": completion_observed["eos_rate"] >= completion_cfg["eos_rate_min"], "parse": completion_observed["parse_rate"] >= completion_cfg["parse_rate_min"], "clipping": completion_observed["clipping_rate"] < completion_cfg["clipping_rate_max_exclusive"]}
    completion_gate = {"thresholds": completion_cfg, "observed": completion_observed, "checks": completion_checks, "pass": all(completion_checks.values())}

    baseline_cfg = cfg["preregistered_gates"]["baseline_reproduction"]
    baseline_checks = {
        "overall": a_overall["fraction_groups_std_gt_zero"] <= baseline_cfg["overall_fraction_groups_std_gt_zero_max"],
        "tool_call": a_strata["action_type"]["tool_call"]["fraction_groups_std_gt_zero"] <= baseline_cfg["tool_call_fraction_groups_std_gt_zero_max"],
        "workflow": a_strata["action_type"]["workflow"]["fraction_groups_std_gt_zero"] <= baseline_cfg["workflow_fraction_groups_std_gt_zero_max"],
    }
    baseline_gate = {"thresholds": baseline_cfg, "observed": {"overall": a_overall["fraction_groups_std_gt_zero"], "tool_call": a_strata["action_type"]["tool_call"]["fraction_groups_std_gt_zero"], "workflow": a_strata["action_type"]["workflow"]["fraction_groups_std_gt_zero"]}, "checks": baseline_checks, "pass": all(baseline_checks.values())}
    b_cfg = cfg["preregistered_gates"]["reward_b_variance"]
    b_checks = {"overall": b_overall["fraction_groups_std_gt_zero"] >= b_cfg["overall_fraction_groups_std_gt_zero_min"], "tool_call_stable": b_strata["action_type"]["tool_call"]["groups"] >= b_cfg["minimum_groups_per_action_stratum"] and b_strata["action_type"]["tool_call"]["fraction_groups_std_gt_zero"] >= b_cfg["tool_call_stable_fraction_min"], "workflow_stable": b_strata["action_type"]["workflow"]["groups"] >= b_cfg["minimum_groups_per_action_stratum"] and b_strata["action_type"]["workflow"]["fraction_groups_std_gt_zero"] >= b_cfg["workflow_stable_fraction_min"]}
    b_gate = {"thresholds": b_cfg, "observed": {"overall": b_overall["fraction_groups_std_gt_zero"], "tool_call": b_strata["action_type"]["tool_call"]["fraction_groups_std_gt_zero"], "workflow": b_strata["action_type"]["workflow"]["fraction_groups_std_gt_zero"]}, "checks": b_checks, "pass": all(b_checks.values())}
    group_diffs = [group["reward_b_structural"]["valid_nonzero_advantage_count"] / group_size - group["reward_a_original"]["valid_nonzero_advantage_count"] / group_size for group in groups]
    bootstrap = paired_bootstrap(group_diffs, int(cfg["bootstrap_seed"]), int(cfg["bootstrap_replicates"]))
    uplift = b_overall["valid_nonzero_advantage_ratio"] - a_overall["valid_nonzero_advantage_ratio"]
    uplift_cfg = cfg["preregistered_gates"]["advantage_uplift"]
    uplift_checks = {"absolute_uplift": uplift >= uplift_cfg["valid_nonzero_advantage_ratio_absolute_uplift_min"], "bootstrap_lower_bound": bootstrap["ci95_lower"] > uplift_cfg["paired_group_bootstrap_lower_bound_min_exclusive"]}
    uplift_gate = {"thresholds": uplift_cfg, "observed_uplift": uplift, "bootstrap": bootstrap, "checks": uplift_checks, "pass": all(uplift_checks.values())}
    paired_rows = [{"sample_id": group["sample_id"], "action_type": group["action_type"], "difficulty": group["difficulty"], "std_a": group["reward_a_original"]["std_population"], "std_b": group["reward_b_structural"]["std_population"], "nonzero_advantage_ratio_a": group["reward_a_original"]["valid_nonzero_advantage_count"] / group_size, "nonzero_advantage_ratio_b": group["reward_b_structural"]["valid_nonzero_advantage_count"] / group_size} for group in groups]
    paired = {"reward_a_overall": a_overall, "reward_b_overall": b_overall, "absolute_valid_nonzero_advantage_uplift": uplift, "paired_group_bootstrap": bootstrap, "per_group": paired_rows}
    all_pass = baseline_gate["pass"] and b_gate["pass"] and uplift_gate["pass"] and completion_gate["pass"]
    decision = "recommend_new_training_preflight" if all_pass else "BLOCKED_DO_NOT_START_GRPO"
    report = {
        "schema_version": "vaguehydro.reward_design.profile.v1", "created_at": datetime.now(timezone.utc).isoformat(), "decision": decision, "all_gates_pass": all_pass,
        "baseline_reproduction_gate": baseline_gate, "reward_b_variance_gate": b_gate, "advantage_uplift_gate": uplift_gate, "workflow_completion_gate": completion_gate,
        "reward_a_overall": a_overall, "reward_b_overall": b_overall, "strata_a": a_strata, "strata_b": b_strata,
        "samples": len(groups), "candidates": sum(group["candidate_count"] for group in groups), "wall_seconds": run_wall, "gpu_peak_memory_bytes": int(torch.cuda.max_memory_allocated()),
        "adapter_fingerprint": {"before": adapter_before, "after": adapter_after, "changed": adapter_before != adapter_after},
        "optimizer_steps": 0, "gradient_updates": 0, "frozen_test_reads": 0, "verifier_calls": 0, "real_expert_calls": 0,
        "interpretation": "All preregistered gates passed; a separately controlled training preflight may be designed." if all_pass else "At least one preregistered gate failed. The reward design remains blocked and GRPO must not start.",
    }
    write_json(output / "PAIRED_COMPARISON.json", paired); write_json(output / "PROFILE_REPORT.json", report)
    (output / "PROFILE_REPORT.md").write_text(markdown_report(report), encoding="utf-8")

    mismatches_a = []; mismatches_b = []
    for group in groups:
        gold = gold_action(records[group["sample_id"]])
        for candidate in group["candidates"]:
            adapted = adapt_completion(candidate["raw_completion"])
            if adapted.valid and adapted.payload is not None:
                recomputed_a = reward_a.score(adapted.payload, gold).to_dict(); recomputed_b = reward_b.score(adapted.payload, gold).to_dict()
            else:
                recomputed_a = {"total": 0.0, **{name: 0.0 for name in A_COMPONENTS}}; recomputed_b = {"total": 0.0, **{name: 0.0 for name in B_COMPONENTS}}
            for name in ("total", *A_COMPONENTS):
                if not math.isclose(float(recomputed_a[name]), float(candidate["reward_a_original"][name]), abs_tol=1e-12): mismatches_a.append([group["sample_id"], candidate["candidate_index"], name])
            for name in ("total", *B_COMPONENTS):
                if not math.isclose(float(recomputed_b[name]), float(candidate["reward_b_structural"][name]), abs_tol=1e-12): mismatches_b.append([group["sample_id"], candidate["candidate_index"], name])
    unit_report = json.loads(paths["unit"].read_text(encoding="utf-8"))
    test_report = {"status": "pass" if not mismatches_a and not mismatches_b and unit_report["status"] == "pass" else "fail", "unit_tests": unit_report, "candidate_count": report["candidates"], "reward_a_recompute_mismatches": len(mismatches_a), "reward_b_recompute_mismatches": len(mismatches_b), "reward_a_mismatches": mismatches_a, "reward_b_mismatches": mismatches_b}
    write_json(output / "TEST_REPORT.json", test_report)
    final_lock = json.loads(paths["lock"].read_text(encoding="utf-8"))
    no_posthoc = {"config_match": sha256_file(config_path) == final_lock["config_sha256"], "plan_match": sha256_file(paths["plan"]) == final_lock["pre_registered_plan_sha256"], "spec_a_match": sha256_file(paths["spec_a"]) == final_lock["reward_spec_a_sha256"], "spec_b_match": sha256_file(paths["spec_b"]) == final_lock["reward_spec_b_sha256"], "manifest_match": sha256_file(paths["manifest"]) == final_lock["data_manifest_sha256"], "reward_b_code_match": sha256_file(root / "hydro_remote_agent/rewards/structural_contrast_reward.py") == final_lock["reward_b_code_sha256"], "sample_ids_match": [group["sample_id"] for group in groups] == [str(row["id"]) for row in manifest["records"]], "selection_used_outputs": False, "selection_used_rewards": False, "posthoc_deleted_samples": 0}
    no_posthoc["status"] = "pass" if all(value for key, value in no_posthoc.items() if key.endswith("match")) else "fail"
    write_json(output / "NO_POSTHOC_AUDIT.json", no_posthoc)
    evidence = {"status": "pass" if test_report["status"] == no_posthoc["status"] == "pass" and adapter_before == adapter_after else "fail", "checks": {"pre_registered": True, "unit_tests_pass": unit_report["status"] == "pass", "reward_a_recompute_exact": not mismatches_a, "reward_b_recompute_exact": not mismatches_b, "m1_train_only": True, "no_posthoc_selection": no_posthoc["status"] == "pass", "adapter_unchanged": adapter_before == adapter_after, "optimizer_zero": True, "gradient_zero": True, "frozen_test_zero": True, "original_reward_separately_recorded": True}}
    write_json(output / "INTEGRITY_EVIDENCE.json", evidence)
    write_json(output / "CODE_HASH.json", {"config": sha256_file(config_path), "prepare": sha256_file(Path(__file__).with_name("prepare_vaguehydro_grpo_reward_design_v1.py")), "profile": sha256_file(Path(__file__)), "reward_a": sha256_file(root / "hydro_remote_agent/rewards/gold_action_reward.py"), "reward_b": sha256_file(root / "hydro_remote_agent/rewards/structural_contrast_reward.py"), "completion_adapter": sha256_file(root / "hydro_remote_agent/rewards/completion_adapter.py"), "decoder_source": sha256_file(root / "hydro_remote_agent/tools/train_vaguehydro_r_m2_grpo_smoke.py")})
    print(json.dumps({"decision": decision, "baseline": baseline_gate["pass"], "reward_b": b_gate["pass"], "uplift": uplift_gate["pass"], "completion": completion_gate["pass"], "integrity": evidence["status"], "output": str(output)}, ensure_ascii=False), flush=True)
    return 0 if evidence["status"] == "pass" else 2


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--project-root", type=Path, required=True); parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(); root = args.project_root.resolve(); config = args.config if args.config.is_absolute() else root / args.config
    return run(config, root)


if __name__ == "__main__":
    raise SystemExit(main())
