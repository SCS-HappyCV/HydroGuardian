"""Inference-only, preregistered VagueHydro reward-variance profiler."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
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
from hydro_remote_agent.schema_constrained_generation import AgentRequestPrefixParser, union_argument_properties
from hydro_remote_agent.schemas.agent_action import AgentActionError, AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.train_vaguehydro_r_m2_grpo_smoke import (
    SchemaConstrainedLogitsProcessor,
    gold_action,
    user_content,
)

COMPONENTS = ("schema", "action", "tool", "argument", "workflow", "stop")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def model_adapter_fingerprint(model: torch.nn.Module) -> str:
    digest = hashlib.sha256()
    count = 0
    for name, parameter in sorted(model.named_parameters()):
        if "lora_" not in name:
            continue
        digest.update(name.encode("utf-8"))
        digest.update(parameter.detach().float().cpu().numpy().tobytes())
        count += 1
    if count == 0:
        raise RuntimeError("No LoRA adapter parameters found")
    return digest.hexdigest()


def load_selected_records(source: Path, identifiers: set[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            identifier = str(row.get("id"))
            if identifier in identifiers:
                found[identifier] = row
    missing = identifiers - set(found)
    if missing:
        raise RuntimeError(f"Manifest IDs missing from M1 train: {sorted(missing)}")
    return found


def make_parser_factory(registry: Any):
    arg_props = union_argument_properties([tool.arguments_schema for tool in registry.tools])
    result_types = {value for tool in registry.tools for value in tool.output.result_types}
    coordinate_spaces = {tool.output.coordinate_space for tool in registry.tools}

    def factory():
        def complete(value: Any) -> bool:
            try:
                AgentRequest.from_dict(value, registry)
                return True
            except (AgentActionError, ValueError, TypeError):
                return False
        return AgentRequestPrefixParser(registry.names(), arg_props, result_types, coordinate_spaces, complete)
    return factory


def summarize_groups(groups: list[dict[str, Any]]) -> dict[str, Any]:
    eps = 1e-12
    candidates = [candidate for group in groups for candidate in group["candidates"]]
    return {
        "groups": len(groups),
        "candidates": len(candidates),
        "fraction_groups_std_gt_zero": sum(group["reward_std_population"] > eps for group in groups) / max(1, len(groups)),
        "zero_variance_rate": sum(group["reward_std_population"] <= eps for group in groups) / max(1, len(groups)),
        "saturated_group_rate": sum(group["reward_min"] == group["reward_max"] and group["reward_max"] >= 1.0 - eps for group in groups) / max(1, len(groups)),
        "saturated_candidate_rate": sum(candidate["rewards"]["total"] >= 1.0 - eps for candidate in candidates) / max(1, len(candidates)),
        "parse_invalid_rate": sum(candidate["parse_invalid"] for candidate in candidates) / max(1, len(candidates)),
        "clipped_rate": sum(candidate["clipped"] for candidate in candidates) / max(1, len(candidates)),
        "eos_rate": sum(candidate["eos_present"] for candidate in candidates) / max(1, len(candidates)),
        "mean_reward": statistics.fmean(candidate["rewards"]["total"] for candidate in candidates) if candidates else 0.0,
        "mean_group_std": statistics.fmean(group["reward_std_population"] for group in groups) if groups else 0.0,
        "advantage_nonzero_ratio": sum(group["advantage_nonzero_count"] for group in groups) / max(1, len(candidates)),
        "unique_raw_ratio": sum(group["unique_raw_count"] for group in groups) / max(1, len(candidates)),
        "unique_token_ratio": sum(group["unique_token_count"] for group in groups) / max(1, len(candidates)),
        "generated_tokens": sum(candidate["token_count"] for candidate in candidates),
        "wall_seconds": sum(group["wall_seconds"] for group in groups),
    }


def build_strata(groups: list[dict[str, Any]], dimensions: list[str]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for dimension in dimensions + ["language", "scene_region", "action_x_difficulty"]:
        cells: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for group in groups:
            key = f"{group['action_type']}|{group['difficulty']}" if dimension == "action_x_difficulty" else str(group[dimension])
            cells[key].append(group)
        output[dimension] = {key: summarize_groups(value) for key, value in sorted(cells.items())}
    return output


def markdown_report(report: Mapping[str, Any]) -> str:
    overall = report["overall"]
    gate = report["preregistered_gate_result"]
    lines = [
        "# VagueHydro GRPO Reward-Variance Profile v1",
        "",
        f"- Status: **{report['status']}**",
        f"- Inference only: `{str(report['inference_only']).lower()}`",
        f"- Samples / candidates: `{overall['groups']}` / `{overall['candidates']}`",
        f"- Groups with reward std > 0: `{overall['fraction_groups_std_gt_zero']:.3f}`",
        f"- Stable variance strata: `{gate['stable_variance_strata_count']}` (required `{gate['minimum_stable_variance_strata']}`)",
        f"- Preregistered gate: **{'PASS' if gate['pass'] else 'FAIL'}**",
        f"- Parse invalid / clipped / EOS rates: `{overall['parse_invalid_rate']:.3f}` / `{overall['clipped_rate']:.3f}` / `{overall['eos_rate']:.3f}`",
        f"- Generated tokens / wall time: `{overall['generated_tokens']}` / `{overall['wall_seconds']:.1f}s`",
        "",
        "## Interpretation",
        "",
        report["interpretation"],
        "",
        "The result is diagnostic evidence about natural within-prompt reward variance. It is not a GRPO training result and does not use the frozen-240 set.",
    ]
    return "\n".join(lines) + "\n"


def run(config_path: Path, root: Path) -> int:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    output = root / cfg["output"]
    plan_path = output / "PRE_REGISTERED_SAMPLING_PLAN.json"
    manifest_path = output / "PROFILE_DATA_MANIFEST.json"
    lock_path = output / "PREREGISTRATION_LOCK.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if sha256_file(plan_path) != lock["plan_sha256"] or sha256_file(manifest_path) != lock["manifest_sha256"]:
        raise RuntimeError("Preregistration hash mismatch before generation")
    if sha256_file(config_path) != lock["config_sha256"]:
        raise RuntimeError("Config changed after preregistration")
    if plan["state"] != "FROZEN_BEFORE_GENERATION" or manifest["state"] != "FROZEN_BEFORE_GENERATION":
        raise RuntimeError("Preregistration state invalid")
    constraints = cfg["constraints"]
    if any(constraints[name] for name in ("formal_training", "optimizer", "gradient_updates", "adapter_updates", "verifier", "real_experts", "frozen_test_reads", "posthoc_sampling_changes", "posthoc_threshold_changes")):
        raise RuntimeError("Forbidden operation enabled in config")

    source = root / cfg["train_source"]
    if sha256_file(source) != lock["source_sha256"]:
        raise RuntimeError("M1 train source changed after preregistration")
    identifiers = {str(row["id"]) for row in manifest["records"]}
    records = load_selected_records(source, identifiers)
    group_size = int(cfg["sampling"]["group_size"])
    if len(manifest["records"]) * group_size != int(manifest["expected_candidate_count"]):
        raise RuntimeError("Manifest candidate count inconsistency")

    raw_path = output / "RAW_CANDIDATES.jsonl"
    groups_path = output / "SAMPLE_PROFILES.jsonl"
    if raw_path.exists() or groups_path.exists():
        raise RuntimeError("Generation artifacts already exist; refusing to overwrite")
    lock["generation_started"] = True
    lock["generation_started_at"] = datetime.now(timezone.utc).isoformat()
    write_json(lock_path, lock)

    registry = load_tool_registry(root / cfg["tool_registry"])
    reward_engine = GoldActionReward(registry, cfg["reward"]["weights"])
    parser_factory = make_parser_factory(registry)
    processor = AutoProcessor.from_pretrained(cfg["base_model"], max_pixels=65536, local_files_only=True)
    processor.tokenizer.padding_side = "left"
    base = Qwen3VLForConditionalGeneration.from_pretrained(
        cfg["base_model"], dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True, low_cpu_mem_usage=True
    )
    model = PeftModel.from_pretrained(base, root / cfg["sft_adapter"], is_trainable=False).to("cuda").eval()
    if any(parameter.requires_grad for parameter in model.parameters()):
        raise RuntimeError("Inference model unexpectedly has trainable parameters")
    adapter_before = model_adapter_fingerprint(model)
    eos_token_id = int(processor.tokenizer.eos_token_id)
    mandatory = [
        "{", "}", "[", "]", ":", ",", '"', "true", "false", "null",
        *AgentRequestPrefixParser.ROOT_KEYS, *AgentRequestPrefixParser.ACTION_KEYS,
        *AgentRequestPrefixParser.STEP_KEYS, *AgentRequestPrefixParser.EXPECTED_KEYS,
        *registry.names(), "1.0", "direct_answer", "tool_call", "workflow", "clarification", "abstain", "auto", "required", "skip",
    ]
    groups: list[dict[str, Any]] = []
    torch.cuda.reset_peak_memory_stats()
    run_started = time.perf_counter()

    for manifest_row in manifest["records"]:
        record = records[str(manifest_row["id"])]
        prompts = [[
            {"role": "system", "content": planner_system_prompt(record)},
            {"role": "user", "content": user_content(record)},
        ] for _ in range(group_size)]
        prompt_copies = deepcopy(prompts)
        for prompt in prompt_copies:
            prepare_multimodal_messages(prompt, num_images=1)
        prompt_texts = [maybe_apply_chat_template({"prompt": prompt}, processor)["prompt"] for prompt in prompt_copies]
        image_path = Path(str(record["images"][0]))
        if not image_path.is_absolute():
            image_path = root / image_path
        with Image.open(image_path) as opened:
            image = opened.convert("RGB")
        inputs = processor(
            text=prompt_texts,
            images=[[image] for _ in range(group_size)],
            return_tensors="pt",
            padding=True,
            padding_side="left",
            max_length=8192,
            truncation=True,
            add_special_tokens=False,
        )
        inputs = {key: value.to("cuda") if torch.is_tensor(value) else value for key, value in inputs.items()}
        prompt_length = int(inputs["input_ids"].size(1))
        logits_processor = SchemaConstrainedLogitsProcessor(
            processor.tokenizer,
            eos_token_id,
            prompt_length,
            parser_factory,
            256,
            int(cfg["decoder"]["fallback_scan_top_tokens"]),
            mandatory,
        )
        seed = int(manifest_row["generation_seed"])
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        started = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                do_sample=bool(cfg["sampling"]["do_sample"]),
                temperature=float(cfg["sampling"]["temperature"]),
                top_p=float(cfg["sampling"]["top_p"]),
                max_new_tokens=int(cfg["sampling"]["max_new_tokens"]),
                logits_processor=[logits_processor],
                pad_token_id=eos_token_id,
                eos_token_id=eos_token_id,
                disable_compile=True,
            )
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
                canonical_sha256 = sha256_text(canonical_json(adapted.payload))
            else:
                breakdown = {"total": 0.0, **{name: 0.0 for name in COMPONENTS}, "invalid": True, "candidate_error": adapted.error}
                canonical_sha256 = None
            rewards = {"total": float(breakdown["total"]), **{name: float(breakdown[name]) for name in COMPONENTS}}
            candidate = {
                "sample_id": str(manifest_row["id"]),
                "manifest_index": int(manifest_row["manifest_index"]),
                "candidate_index": candidate_index,
                "generation_seed": seed,
                "raw_completion": raw,
                "raw_sha256": sha256_text(raw),
                "token_ids": token_ids,
                "token_sha256": sha256_text(canonical_json(token_ids)),
                "canonical_sha256": canonical_sha256,
                "token_count": len(token_ids),
                "eos_present": eos_position is not None,
                "eos_position": eos_position,
                "clipped": eos_position is None and len(token_ids) >= int(cfg["sampling"]["max_new_tokens"]),
                "parse_invalid": not adapted.valid,
                "parse_error": adapted.error,
                "rewards": rewards,
            }
            candidates.append(candidate)
            totals.append(rewards["total"])
            append_jsonl(raw_path, candidate)
        mean = statistics.fmean(totals)
        std_population = statistics.pstdev(totals)
        std_sample = statistics.stdev(totals) if len(totals) > 1 else 0.0
        advantages = [(value - mean) / std_population if std_population > 1e-12 else 0.0 for value in totals]
        group = {
            **{key: manifest_row[key] for key in ("id", "manifest_index", "action_type", "difficulty", "ambiguity_level", "language", "scene_region", "parameter_slots", "parameter_complexity", "generation_seed")},
            "sample_id": str(manifest_row["id"]),
            "candidate_count": len(candidates),
            "unique_raw_count": len({candidate["raw_sha256"] for candidate in candidates}),
            "unique_token_count": len({candidate["token_sha256"] for candidate in candidates}),
            "unique_canonical_count": len({candidate["canonical_sha256"] for candidate in candidates if candidate["canonical_sha256"]}),
            "reward_mean": mean,
            "reward_min": min(totals),
            "reward_max": max(totals),
            "reward_std_population": std_population,
            "reward_std_sample": std_sample,
            "advantages": advantages,
            "advantage_nonzero_count": sum(abs(value) > 1e-12 for value in advantages),
            "wall_seconds": wall_seconds,
            "candidates": candidates,
        }
        groups.append(group)
        append_jsonl(groups_path, group)
        print(json.dumps({"completed": len(groups), "total": len(manifest["records"]), "id": group["sample_id"], "std": std_population, "unique": group["unique_raw_count"], "seconds": wall_seconds}), flush=True)

    adapter_after = model_adapter_fingerprint(model)
    run_wall = time.perf_counter() - run_started
    dimensions = list(cfg["preregistered_gate"]["stability_stratum_dimensions"])
    overall = summarize_groups(groups)
    overall["end_to_end_wall_seconds"] = run_wall
    overall["tokens_per_second"] = overall["generated_tokens"] / max(run_wall, 1e-9)
    overall["gpu_peak_memory_bytes"] = int(torch.cuda.max_memory_allocated())
    strata = build_strata(groups, dimensions)
    gate_cfg = cfg["preregistered_gate"]
    stable = []
    for dimension in dimensions:
        for key, summary in strata[dimension].items():
            if summary["groups"] >= int(gate_cfg["stable_stratum_min_groups"]) and summary["fraction_groups_std_gt_zero"] >= float(gate_cfg["stable_stratum_fraction_std_gt_zero_min"]):
                stable.append(f"{dimension}={key}")
    gate_result = {
        "overall_fraction_groups_std_gt_zero": overall["fraction_groups_std_gt_zero"],
        "overall_minimum": float(gate_cfg["overall_fraction_groups_std_gt_zero_min"]),
        "stable_variance_strata": stable,
        "stable_variance_strata_count": len(stable),
        "minimum_stable_variance_strata": int(gate_cfg["minimum_stable_variance_strata"]),
    }
    gate_result["pass"] = gate_result["overall_fraction_groups_std_gt_zero"] >= gate_result["overall_minimum"] and len(stable) >= gate_result["minimum_stable_variance_strata"]
    interpretation = (
        "The preregistered variance gate passed: natural candidate diversity is sufficient to justify a later GRPO run."
        if gate_result["pass"] else
        "The preregistered variance gate failed: this sampling/decoder policy does not provide enough natural reward contrast for GRPO; training should not be claimed or started from this profile."
    )
    report = {
        "schema_version": "vaguehydro.grpo_variance_profile.report.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if gate_result["pass"] else "fail_gate",
        "inference_only": True,
        "formal_training": False,
        "optimizer_steps": 0,
        "gradient_updates": 0,
        "frozen_test_reads": 0,
        "verifier_calls": 0,
        "real_expert_calls": 0,
        "overall": overall,
        "strata": strata,
        "preregistered_gate_result": gate_result,
        "adapter_fingerprint": {"before": adapter_before, "after": adapter_after, "changed": adapter_before != adapter_after},
        "interpretation": interpretation,
    }
    write_json(output / "STRATUM_AGGREGATES.json", strata)
    write_json(output / "VARIANCE_PROFILE_REPORT.json", report)
    (output / "VARIANCE_PROFILE_REPORT.md").write_text(markdown_report(report), encoding="utf-8")

    recompute_mismatches = []
    for group in groups:
        gold = gold_action(records[group["sample_id"]])
        for candidate in group["candidates"]:
            adapted = adapt_completion(candidate["raw_completion"])
            recomputed = reward_engine.score(adapted.payload, gold).to_dict() if adapted.valid and adapted.payload is not None else {"total": 0.0, **{name: 0.0 for name in COMPONENTS}}
            for name in ("total", *COMPONENTS):
                if not math.isclose(float(recomputed[name]), float(candidate["rewards"][name]), abs_tol=1e-12):
                    recompute_mismatches.append({"sample_id": group["sample_id"], "candidate_index": candidate["candidate_index"], "component": name})
    reward_audit = {"status": "pass" if not recompute_mismatches else "fail", "candidate_count": overall["candidates"], "mismatch_count": len(recompute_mismatches), "mismatches": recompute_mismatches}
    write_json(output / "REWARD_RECOMPUTE_AUDIT.json", reward_audit)
    final_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    no_posthoc = {
        "status": "pass",
        "plan_sha256_matches": sha256_file(plan_path) == final_lock["plan_sha256"],
        "manifest_sha256_matches": sha256_file(manifest_path) == final_lock["manifest_sha256"],
        "config_sha256_matches": sha256_file(config_path) == final_lock["config_sha256"],
        "sample_ids_match": [group["sample_id"] for group in groups] == [str(row["id"]) for row in manifest["records"]],
        "group_size_match": all(group["candidate_count"] == group_size for group in groups),
        "thresholds_source": "pre_registered_config",
        "posthoc_changes": 0,
    }
    no_posthoc["status"] = "pass" if all(value for key, value in no_posthoc.items() if key.endswith("_match") or key.endswith("_matches")) else "fail"
    write_json(output / "NO_POSTHOC_AUDIT.json", no_posthoc)
    code_hash = {
        "config": sha256_file(config_path),
        "prepare_script": sha256_file(Path(__file__).with_name("prepare_vaguehydro_grpo_variance_profile_v1.py")),
        "profile_script": sha256_file(Path(__file__)),
        "completion_adapter": sha256_file(root / "hydro_remote_agent/rewards/completion_adapter.py"),
        "gold_action_reward": sha256_file(root / "hydro_remote_agent/rewards/gold_action_reward.py"),
        "schema_decoder_source": sha256_file(root / "hydro_remote_agent/tools/train_vaguehydro_r_m2_grpo_smoke.py"),
    }
    write_json(output / "CODE_HASH.json", code_hash)
    audit = {
        "status": "pass" if reward_audit["status"] == "pass" and no_posthoc["status"] == "pass" and adapter_before == adapter_after else "fail",
        "checks": {
            "pre_registered_before_generation": True,
            "no_posthoc_changes": no_posthoc["status"] == "pass",
            "reward_recompute_exact": reward_audit["status"] == "pass",
            "adapter_unchanged": adapter_before == adapter_after,
            "optimizer_steps_zero": True,
            "gradient_updates_zero": True,
            "frozen_test_reads_zero": True,
            "real_model_and_sft_adapter": True,
            "schema_constrained_decoder": True,
            "gold_action_reward": True,
        },
    }
    write_json(output / "EXPERIMENT_AUDIT.json", audit)
    test_report = {"status": audit["status"], "expected_groups": len(manifest["records"]), "observed_groups": len(groups), "expected_candidates": manifest["expected_candidate_count"], "observed_candidates": overall["candidates"], "gate_pass": gate_result["pass"]}
    write_json(output / "TEST_REPORT.json", test_report)
    (output / "TEST_REPORT.md").write_text("# Test Report\n\n" + "\n".join(f"- {key}: `{value}`" for key, value in test_report.items()) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "audit": audit["status"], "gate": gate_result, "output": str(output)}, ensure_ascii=False), flush=True)
    return 0 if audit["status"] == "pass" else 2


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
