from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.rewards.request_canonicalizer import canonicalize_agent_request
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


COMPONENTS = ("schema", "action", "tool", "argument", "workflow", "stop")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_record(path: Path, sample_id: str) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                if str(record.get("id")) == sample_id:
                    return record
    raise ValueError(f"Sample {sample_id} not found in {path}")


def gold_action(record: Mapping[str, Any]) -> Mapping[str, Any]:
    for message in reversed(record["messages"]):
        if message.get("role") == "assistant":
            value = json.loads(message["content"])
            if isinstance(value, dict):
                return value
    raise ValueError("Selected record has no gold assistant action")


def float_list(values: Sequence[Any]) -> list[float]:
    return [float(value) for value in values]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Seal VagueHydro-R M3 native-policy smoke evidence.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = read_json(config_path)
    output_dir = root / config["output_dir"]
    base_report = read_json(output_dir / "SMOKE_REPORT.json")
    exit_code = int((output_dir / "train.exit_code").read_text(encoding="utf-8").strip())
    logs_path = output_dir / "reward_log_history.json"
    logs = read_json(logs_path) if logs_path.is_file() else {}
    prompts = list(logs.get("prompts", []))
    completions = list(logs.get("completions", []))
    advantages = float_list(logs.get("advantages", []))
    sample_ids = list(base_report.get("data", {}).get("sample_ids", []))
    records = {
        sample_id: find_record(root / config["train"], sample_id)
        for sample_id in sample_ids
    }
    registry = load_tool_registry(root / config["tool_registry"])
    reward_engine = GoldActionReward(registry, config["reward_weights"])
    candidate_items = []
    total_rewards = []
    candidate_counts = {sample_id: 0 for sample_id in sample_ids}
    for index, completion in enumerate(completions):
        prompt = str(prompts[index]) if index < len(prompts) else ""
        matches = [sample_id for sample_id in sample_ids if sample_id in prompt]
        if len(matches) != 1:
            raise ValueError(f"Could not uniquely map completion {index} to a selected sample: {matches}")
        sample_id = matches[0]
        record = records[sample_id]
        gold = gold_action(record)
        allowed_actions = [str(gold.get("action", {}).get("type", ""))]
        canonical = canonicalize_agent_request(completion, registry)
        reward = reward_engine.score(completion, gold, allowed_actions=allowed_actions)
        total_rewards.append(float(reward.total))
        candidate_items.append(
            {
                "candidate_index": index,
                "candidate_index_within_prompt": candidate_counts[sample_id],
                "sample_id": sample_id,
                "source_split": config["data"]["split"],
                "gold_action_type": str(gold.get("action", {}).get("type", "")),
                "raw_completion": completion,
                "parse_valid": canonical.valid,
                "invalid_reason": canonical.error or reward.candidate_error,
                "canonical_request": canonical.to_dict(),
                "reward_components": reward.to_dict(),
                "total_reward": float(reward.total),
            }
        )
        candidate_counts[sample_id] += 1
    rewards_by_sample = {
        sample_id: [item["total_reward"] for item in candidate_items if item["sample_id"] == sample_id]
        for sample_id in sample_ids
    }
    per_sample_reward_std = {
        sample_id: (
            float(__import__("statistics").stdev(values)) if len(values) > 1 else 0.0
        )
        for sample_id, values in rewards_by_sample.items()
    }
    candidate_evidence = {
        "schema_version": "vaguehydro_r.m3_policy_candidates.v1",
        "generation_mode": config["grpo"]["generation_mode"],
        "policy_samples": True,
        "forced_completions": False,
        "trainer_class": "trl.GRPOTrainer",
        "sampling_stack": "Qwen3VLForConditionalGeneration.generate via TRL 0.24.0 _generate_single_turn",
        "sample_ids": sample_ids,
        "source_split": config["data"]["split"],
        "seed": config["seed"],
        "num_candidates": len(candidate_items),
        "candidates_per_sample": candidate_counts,
        "per_sample_reward_std": per_sample_reward_std,
        "candidates": candidate_items,
    }
    write_json(output_dir / "candidate_reward_evidence.json", candidate_evidence)

    checkpoint_adapter = output_dir / "trainer" / "checkpoint-1" / "adapter_model.safetensors"
    initial_adapter = root / config["sft_adapter"] / "adapter_model.safetensors"
    initial_sha = sha256_file(initial_adapter) if initial_adapter.is_file() else None
    checkpoint_sha = sha256_file(checkpoint_adapter) if checkpoint_adapter.is_file() else None
    adapter_changed = bool(initial_sha and checkpoint_sha and initial_sha != checkpoint_sha)
    adapter_delta = {
        "initial_adapter": str(initial_adapter),
        "initial_sha256": initial_sha,
        "checkpoint_adapter": str(checkpoint_adapter),
        "checkpoint_sha256": checkpoint_sha,
        "changed": adapter_changed,
    }
    write_json(output_dir / "adapter_delta.json", adapter_delta)

    reward_std = float(base_report.get("training", {}).get("reward_std", 0.0))
    gradient_norm = base_report.get("training", {}).get("gradient_norm")
    nonzero_advantages = sum(not math.isclose(value, 0.0, abs_tol=1e-8) for value in advantages)
    expected_candidate_count = len(sample_ids) * int(config["grpo"]["num_generations"])
    raw_training_rewards = base_report.get("training", {}).get("total_rewards", [])
    checks = {
        "native_policy_sampling": config["grpo"]["generation_mode"] == "native_policy_sampling"
        and config["constraints"]["policy_samples"]
        and not config["constraints"]["forced_completions"],
        "candidate_count_gte_2": len(candidate_items) >= 2,
        "candidate_evidence_complete": len(candidate_items) == expected_candidate_count
        and all(value == int(config["grpo"]["num_generations"]) for value in candidate_counts.values()),
        "reward_recomputation_matches": len(total_rewards) == len(raw_training_rewards) == expected_candidate_count
        and all(
            math.isclose(left, right, abs_tol=1e-6)
            for left, right in zip(total_rewards, raw_training_rewards)
        ),
        "positive_reward_variance": reward_std > 0.0
        and any(value > 0.0 for value in per_sample_reward_std.values()),
        "nonzero_advantage": nonzero_advantages > 0,
        "nonzero_gradient": gradient_norm is not None and math.isfinite(float(gradient_norm)) and float(gradient_norm) > 0.0,
        "adapter_changed": adapter_changed,
        "checkpoint_and_optimizer": checkpoint_adapter.is_file()
        and (output_dir / "trainer" / "checkpoint-1" / "optimizer.pt").is_file(),
        "global_step_within_controlled_limit": 1 <= int(base_report.get("training", {}).get("global_step", 0)) <= 2,
        "frozen_test_not_used": base_report.get("data", {}).get("frozen_test_samples") == 0,
        "no_expert_or_verifier": not base_report.get("called_real_experts", True)
        and not base_report.get("called_verifier", True),
        "m1_unchanged": bool(base_report.get("checks", {}).get("m1_unchanged", False)),
        "exit_code_zero": exit_code == 0,
    }
    ready = all(checks.values())
    gaps = []
    if not checks["positive_reward_variance"]:
        gaps.append("Native policy samples did not produce nonzero Gold-Action reward variance; rewards were not modified.")
    if not checks["nonzero_advantage"]:
        gaps.append("Native policy samples produced no nonzero advantage.")
    if not checks["nonzero_gradient"]:
        gaps.append("No positive finite gradient norm was recorded.")
    if not checks["adapter_changed"]:
        gaps.append("The checkpoint adapter is absent or byte-identical to the initial SFT adapter.")
    if exit_code != 0:
        gaps.append(f"Training command exited with code {exit_code}.")
    for name, passed in checks.items():
        if not passed and not any(name.replace("_", " ") in gap.lower() for gap in gaps):
            gaps.append(f"Gate failed: {name}.")

    trainer_logs = list(logs.get("trainer_log_history", []))
    clipped_ratio = next(
        (float(item["completions/clipped_ratio"]) for item in trainer_logs if "completions/clipped_ratio" in item),
        None,
    )
    parse_valid_count = sum(bool(item["parse_valid"]) for item in candidate_items)
    all_rewards_perfect = bool(total_rewards) and all(math.isclose(value, 1.0, abs_tol=1e-8) for value in total_rewards)
    if checks["positive_reward_variance"]:
        saturation_analysis = "Natural policy samples produced within-prompt Gold-Action reward variance."
    elif parse_valid_count == 0:
        saturation_analysis = "All completions failed parsing/schema validation; parsing format is the primary blocker."
    elif clipped_ratio is not None and clipped_ratio > 0.0:
        saturation_analysis = "At least one completion was length-clipped; generation length may be the primary blocker."
    elif all_rewards_perfect:
        saturation_analysis = "All parsed completions matched their Gold-Action targets exactly; reward saturation is the primary blocker."
    else:
        saturation_analysis = "Completions received equal non-perfect rewards; prompt/data coverage or reward resolution is the primary blocker."
    report = {
        "schema_version": "vaguehydro_r.m3_controlled_smoke_report.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready_for_m3_controlled" if ready else "blocked",
        "ready_for_m3_controlled": ready,
        "scope": "single-seed single-prompt native-policy controlled smoke; not formal training evidence",
        "parent_m2_limitation_preserved": "M2 forced completions proved only the mechanical path and were not policy samples.",
        "seed": config["seed"],
        "exit_code": exit_code,
        "gpu": base_report.get("gpu"),
        "data": base_report.get("data"),
        "training": {
            **base_report.get("training", {}),
            "total_rewards_recomputed": total_rewards,
            "per_sample_reward_std": per_sample_reward_std,
            "nonzero_advantage_count": nonzero_advantages,
            "adapter_changed": adapter_changed,
        },
        "diagnostics": {
            "parse_valid_count": parse_valid_count,
            "parse_invalid_count": len(candidate_items) - parse_valid_count,
            "unique_raw_completion_count": len({item["raw_completion"] for item in candidate_items}),
            "completion_clipped_ratio": clipped_ratio,
            "all_rewards_perfect": all_rewards_perfect,
            "saturation_analysis": saturation_analysis,
        },
        "called_real_experts": False,
        "called_verifier": False,
        "checks": checks,
        "m1_preservation": base_report.get("m1_preservation", {}),
        "implementation_hashes": {
            **base_report.get("implementation_hashes", {}),
            "m3_config": sha256_file(config_path),
            "m3_sealer": sha256_file(Path(__file__)),
        },
        "artifacts": {
            "candidate_reward_evidence": str((output_dir / "candidate_reward_evidence.json").relative_to(root)),
            "reward_history": str(logs_path.relative_to(root)),
            "trainer_state": str((output_dir / "trainer_state.json").relative_to(root)),
            "checkpoint": str((output_dir / "trainer" / "checkpoint-1").relative_to(root)),
            "adapter_delta": str((output_dir / "adapter_delta.json").relative_to(root)),
        },
        "gaps": gaps,
    }
    write_json(output_dir / "M3_REPORT.json", report)
    (output_dir / "M3_REPORT.md").write_text(
        "\n".join(
            [
                "# VagueHydro-R M3 Controlled Smoke Report",
                "",
                f"- Status: **{'READY_FOR_M3_CONTROLLED' if ready else 'BLOCKED'}**",
                "- Sampling: native Qwen3-VL policy sampling through `trl.GRPOTrainer`",
                f"- Seed: `{config['seed']}`",
                f"- Samples / candidates: `{base_report.get('data', {}).get('unique_samples', 0)}` / `{len(candidate_items)}`",
                f"- Reward std: `{reward_std}`",
                f"- Nonzero advantages: `{nonzero_advantages}`",
                f"- Gradient norm: `{gradient_norm}`",
                f"- Adapter changed: `{adapter_changed}`",
                f"- Exit code: `{exit_code}`",
                "- Frozen-test samples: `0`",
                "- Real experts / Verifier: `False / False`",
                "",
                "This is a one-seed controlled-path smoke, not multi-seed formal training evidence.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (output_dir / "GAP_LIST.md").write_text(
        "# VagueHydro-R M3 Gap List\n\n" + ("\n".join(f"- {gap}" for gap in gaps) if gaps else "- None for the controlled smoke gate.") + "\n",
        encoding="utf-8",
    )
    print(report["status"])
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
