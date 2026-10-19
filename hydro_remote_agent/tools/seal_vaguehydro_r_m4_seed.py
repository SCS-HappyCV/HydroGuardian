from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.rewards.request_canonicalizer import canonicalize_agent_request
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


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


def artifact_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)).replace("\\", "/"),
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path) if path.is_file() else None,
        "exists": path.is_file(),
    }


def sample_std(values: Sequence[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Seal one VagueHydro-R M4 policy-sampling seed.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = read_json(config_path)
    output_dir = root / config["output_dir"]
    base_report = read_json(output_dir / "SMOKE_REPORT.json")
    reward_history = read_json(output_dir / "reward_log_history.json")
    trace = read_json(output_dir / "policy_sampling_trace.json")
    train_exit_code = int((output_dir / "train.exit_code").read_text(encoding="utf-8").strip())
    registry = load_tool_registry(root / config["tool_registry"])
    reward_engine = GoldActionReward(registry, config["reward_weights"])

    candidates = []
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for index, item in enumerate(trace):
        gold = json.loads(item["gold_action_json"])
        canonical = canonicalize_agent_request(item["raw_completion"], registry)
        reward = reward_engine.score(
            item["raw_completion"],
            gold,
            allowed_actions=[str(gold.get("action", {}).get("type", ""))],
        )
        candidate = {
            "candidate_index": index,
            "generation_batch_index": int(item["generation_batch_index"]),
            "candidate_index_in_batch": int(item["candidate_index_in_batch"]),
            "sample_id": str(item["sample_id"]),
            "source_split": str(item["source_split"]),
            "gold_action_type": str(gold.get("action", {}).get("type", "")),
            "raw_completion": item["raw_completion"],
            "raw_completion_token_ids": list(item.get("raw_completion_token_ids", [])),
            "completion_token_count": int(item["completion_token_count"]),
            "ended_with_eos": bool(item.get("ended_with_eos", False)),
            "ended_with_pad": bool(item.get("ended_with_pad", False)),
            "hit_length_limit": bool(item.get("hit_length_limit", item["clipped"])),
            "complete_json_detected": bool(item.get("complete_json_detected", canonical.valid)),
            "constraint_state": item.get("constraint_state"),
            "clipped": bool(item["clipped"]),
            "parse_valid": bool(canonical.valid),
            "invalid_reason": canonical.error or reward.candidate_error,
            "canonical_request": canonical.to_dict(),
            "reward_components": reward.to_dict(),
            "total_reward": float(reward.total),
            "advantage": float(item["advantage"]),
        }
        candidates.append(candidate)
        grouped.setdefault((candidate["generation_batch_index"], candidate["sample_id"]), []).append(candidate)

    group_size = int(config["grpo"]["num_generations"])
    max_steps = int(config["grpo"]["max_steps"])
    sample_ids = [str(value) for value in config["data"]["sample_ids"]]
    expected_count = len(sample_ids) * group_size * max_steps
    group_summaries = []
    for (generation_index, sample_id), values in sorted(grouped.items()):
        rewards = [item["total_reward"] for item in values]
        group_summaries.append(
            {
                "generation_batch_index": generation_index,
                "sample_id": sample_id,
                "candidate_count": len(values),
                "reward_mean": statistics.fmean(rewards),
                "reward_std": sample_std(rewards),
                "reward_min": min(rewards),
                "reward_max": max(rewards),
                "invalid_count": sum(not item["parse_valid"] for item in values),
                "clipped_count": sum(item["clipped"] for item in values),
                "eos_count": sum(item["ended_with_eos"] for item in values),
                "complete_json_count": sum(item["complete_json_detected"] for item in values),
                "nonzero_advantage_count": sum(
                    not math.isclose(item["advantage"], 0.0, abs_tol=1e-8) for item in values
                ),
            }
        )

    rewards = [item["total_reward"] for item in candidates]
    advantages = [item["advantage"] for item in candidates]
    invalid_count = sum(not item["parse_valid"] for item in candidates)
    clipped_count = sum(item["clipped"] for item in candidates)
    eos_count = sum(item["ended_with_eos"] for item in candidates)
    complete_json_count = sum(item["complete_json_detected"] for item in candidates)
    constraint_complete_count = sum(
        bool((item.get("constraint_state") or {}).get("complete")) for item in candidates
    )
    trainer_state = read_json(output_dir / "trainer_state.json")
    gradient_norms = [
        float(item["grad_norm"])
        for item in trainer_state.get("log_history", [])
        if "grad_norm" in item and math.isfinite(float(item["grad_norm"]))
    ]
    positive_gradient_norms = [value for value in gradient_norms if value > 0.0]
    checkpoint_path = root / base_report["artifacts"]["trainer_checkpoint"]
    checkpoint_adapter = checkpoint_path / "adapter_model.safetensors"
    optimizer_path = checkpoint_path / "optimizer.pt"
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

    logged_rewards = [float(value) for value in base_report.get("training", {}).get("total_rewards", [])]
    checks = {
        "native_policy_sampling": config["grpo"]["generation_mode"] == "native_policy_sampling"
        and config["constraints"]["policy_samples"]
        and not config["constraints"]["forced_completions"],
        "all_candidates_retained": len(candidates) == expected_count,
        "all_prompt_groups_complete": len(grouped) == len(sample_ids) * max_steps
        and all(len(values) == group_size for values in grouped.values()),
        "reward_recomputation_matches": len(logged_rewards) == len(rewards)
        and all(math.isclose(left, right, abs_tol=1e-6) for left, right in zip(logged_rewards, rewards)),
        "at_least_one_positive_group_reward_std": any(item["reward_std"] > 0.0 for item in group_summaries),
        "at_least_one_nonzero_advantage": any(not math.isclose(value, 0.0, abs_tol=1e-8) for value in advantages),
        "at_least_one_finite_positive_gradient": bool(positive_gradient_norms),
        "adapter_changed": adapter_changed,
        "checkpoint_and_optimizer": checkpoint_adapter.is_file() and optimizer_path.is_file(),
        "optimizer_steps_in_range": 2 <= int(base_report.get("training", {}).get("global_step", 0)) <= 5,
        "frozen_test_not_used": base_report.get("data", {}).get("frozen_test_samples") == 0,
        "m1_unchanged": bool(base_report.get("checks", {}).get("m1_unchanged", False)),
        "no_expert_or_verifier": not base_report.get("called_real_experts", True)
        and not base_report.get("called_verifier", True),
        "train_exit_code_zero": train_exit_code == 0,
        "clipping_rate_strictly_below_10_percent": bool(candidates)
        and clipped_count / len(candidates) < 0.10,
        "schema_constraint_completed_all_candidates": not bool(
            config["grpo"].get("schema_constrained_generation", False)
        )
        or constraint_complete_count == len(candidates),
        "all_candidates_parse_valid_under_schema_constraint": not bool(
            config["grpo"].get("schema_constrained_generation", False)
        )
        or invalid_count == 0,
    }
    passed = all(checks.values())
    candidate_evidence = {
        "schema_version": "vaguehydro_r.m4_seed_candidates.v1",
        "seed": int(config["seed"]),
        "policy_samples": True,
        "forced_completions": False,
        "source_split": config["data"]["split"],
        "sample_ids": sample_ids,
        "group_size": group_size,
        "optimizer_steps": max_steps,
        "candidate_count": len(candidates),
        "group_summaries": group_summaries,
        "candidates": candidates,
    }
    write_json(output_dir / "candidate_reward_evidence.json", candidate_evidence)

    gaps = [f"Gate failed: {name}." for name, value in checks.items() if not value]
    report = {
        "schema_version": "vaguehydro_r.m4_seed_report.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": int(config["seed"]),
        "status": "pass" if passed else "blocked",
        "pilot_seed_pass": passed,
        "scope": "short native-policy pilot seed; not formal training or final quality evidence",
        "train_exit_code": train_exit_code,
        "data": base_report.get("data", {}),
        "sampling": {
            "do_sample": config["grpo"]["do_sample"],
            "group_size": group_size,
            "temperature": config["grpo"]["temperature"],
            "top_p": config["grpo"]["top_p"],
            "max_new_tokens": config["grpo"]["max_new_tokens"],
            "stop_on_complete_json": bool(config["grpo"].get("stop_on_complete_json", False)),
            "json_termination_mode": config["grpo"].get("json_termination_mode", "disabled"),
            "schema_constrained_generation": bool(
                config["grpo"].get("schema_constrained_generation", False)
            ),
            "constraint_max_allowed_tokens": config["grpo"].get("constraint_max_allowed_tokens"),
            "constraint_scan_top_tokens": config["grpo"].get("constraint_scan_top_tokens"),
        },
        "training": {
            "global_step": base_report.get("training", {}).get("global_step"),
            "train_loss": base_report.get("training", {}).get("train_loss"),
            "gradient_norm_history": gradient_norms,
            "positive_gradient_norm_count": len(positive_gradient_norms),
            "adapter_changed": adapter_changed,
            "initial_adapter_sha256": initial_sha,
            "checkpoint_adapter_sha256": checkpoint_sha,
        },
        "rewards": {
            "candidate_count": len(rewards),
            "mean": statistics.fmean(rewards) if rewards else 0.0,
            "std": sample_std(rewards),
            "min": min(rewards) if rewards else None,
            "max": max(rewards) if rewards else None,
            "nonzero_advantage_count": sum(not math.isclose(value, 0.0, abs_tol=1e-8) for value in advantages),
            "positive_variance_group_count": sum(item["reward_std"] > 0.0 for item in group_summaries),
        },
        "quality": {
            "invalid_parse_count": invalid_count,
            "invalid_parse_rate": invalid_count / len(candidates) if candidates else 1.0,
            "clipped_count": clipped_count,
            "clipping_rate": clipped_count / len(candidates) if candidates else 1.0,
            "ended_with_eos_count": eos_count,
            "ended_with_eos_rate": eos_count / len(candidates) if candidates else 0.0,
            "complete_json_detected_count": complete_json_count,
            "complete_json_detected_rate": complete_json_count / len(candidates) if candidates else 0.0,
            "constraint_complete_count": constraint_complete_count,
            "constraint_complete_rate": constraint_complete_count / len(candidates) if candidates else 0.0,
        },
        "gpu": base_report.get("gpu", {}),
        "called_real_experts": False,
        "called_verifier": False,
        "checks": checks,
        "m1_preservation": base_report.get("m1_preservation", {}),
        "artifacts": {
            "checkpoint": str(checkpoint_path.relative_to(root)),
            "candidate_reward_evidence": str((output_dir / "candidate_reward_evidence.json").relative_to(root)),
            "reward_history": str((output_dir / "reward_log_history.json").relative_to(root)),
            "policy_sampling_trace": str((output_dir / "policy_sampling_trace.json").relative_to(root)),
            "trainer_state": str((output_dir / "trainer_state.json").relative_to(root)),
            "adapter_delta": str((output_dir / "adapter_delta.json").relative_to(root)),
            "remote_verifiable_files": {
                "raw_train_jsonl": artifact_record(root / config["train"], root),
                "checkpoint_adapter": artifact_record(checkpoint_adapter, root),
                "optimizer": artifact_record(optimizer_path, root),
            },
        },
        "gaps": gaps,
    }
    write_json(output_dir / "SEED_REPORT.json", report)
    (output_dir / "SEED_REPORT.md").write_text(
        "\n".join(
            [
                f"# VagueHydro-R M4 Seed {config['seed']}",
                "",
                f"- Status: **{'PASS' if passed else 'BLOCKED'}**",
                f"- Optimizer steps: `{report['training']['global_step']}`",
                f"- Candidates: `{len(candidates)}`",
                f"- Reward mean / std: `{report['rewards']['mean']}` / `{report['rewards']['std']}`",
                f"- Nonzero advantages: `{report['rewards']['nonzero_advantage_count']}`",
                f"- Positive gradient records: `{len(positive_gradient_norms)}`",
                f"- Invalid / clipping rate: `{report['quality']['invalid_parse_rate']}` / `{report['quality']['clipping_rate']}`",
                f"- EOS / complete-JSON rate: `{report['quality']['ended_with_eos_rate']}` / `{report['quality']['complete_json_detected_rate']}`",
                f"- Peak GPU GiB: `{report['gpu'].get('peak_memory_gib')}`",
                f"- Adapter changed: `{adapter_changed}`",
                f"- Train exit code: `{train_exit_code}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (output_dir / "GAP_LIST.md").write_text(
        "# Seed Gap List\n\n" + ("\n".join(f"- {gap}" for gap in gaps) if gaps else "- None for the per-seed pilot gate.") + "\n",
        encoding="utf-8",
    )
    print("pass" if passed else "blocked")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
