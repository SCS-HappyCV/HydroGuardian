from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_ids(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8") as handle:
        return {str(json.loads(line).get("id")) for line in handle if line.strip()}


def selected_metadata(path: Path, sample_ids: Sequence[str]) -> list[dict[str, Any]]:
    requested = set(sample_ids)
    found = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            identifier = str(record.get("id"))
            if identifier not in requested:
                continue
            assistant = next(message for message in reversed(record["messages"]) if message.get("role") == "assistant")
            action = json.loads(assistant["content"])
            found[identifier] = {
                "id": identifier,
                "source_line": line_number,
                "action_type": str(action.get("action", {}).get("type", "")),
                "images": list(record.get("images", [])),
            }
    missing = [identifier for identifier in sample_ids if identifier not in found]
    if missing:
        raise ValueError(f"Frozen M4 sample IDs missing from train source: {missing}")
    return [found[identifier] for identifier in sample_ids]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare frozen VagueHydro-R M4 pilot configs and data manifest.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    freeze_path = args.freeze if args.freeze.is_absolute() else root / args.freeze
    freeze = read_json(freeze_path)
    parent = freeze_path.parent
    m1_manifest_path = root / "runs/hydro_remote_agent/vaguehydro_r_m1_v1/rl_data_manifest.json"
    m1_manifest = read_json(m1_manifest_path)
    train_path = root / "hydro_remote_agent/data/vague_hydro_sft_v2/train_curriculum_16360.jsonl"
    valid_path = root / "hydro_remote_agent/data/vague_hydro_sft_v2/val_sft.jsonl"
    frozen_path = root / "runs/hydro_remote_agent/agent_eval_v1/gold_240.jsonl"
    source_paths = {"train": train_path, "valid": valid_path, "frozen": frozen_path}
    expected = {
        "train": m1_manifest["sources"]["train"]["sha256"],
        "valid": m1_manifest["sources"]["valid"]["sha256"],
        "frozen": m1_manifest["sources"]["frozen_test_exclusion_only"]["sha256"],
    }
    actual = {name: sha256_file(path) for name, path in source_paths.items()}
    if actual != expected:
        raise ValueError(f"M1 source hash mismatch: expected={expected} actual={actual}")
    sample_ids = [str(value) for value in freeze["data"]["sample_ids"]]
    frozen_ids = read_ids(frozen_path)
    overlaps = sorted(set(sample_ids) & frozen_ids)
    if overlaps:
        raise ValueError(f"M4 samples overlap frozen test: {overlaps}")
    samples = selected_metadata(train_path, sample_ids)
    data_manifest = {
        "schema_version": "vaguehydro_r.m4_data_manifest.v1",
        "split": "train",
        "sample_count": len(samples),
        "samples": samples,
        "source_sha256": actual,
        "source_artifacts": {
            name: {
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": actual[name],
            }
            for name, path in source_paths.items()
        },
        "m1_manifest": str(m1_manifest_path.relative_to(root)),
        "frozen_test_sample_count": 0,
        "frozen_overlap_ids": overlaps,
        "selection_policy": "fixed explicit IDs inherited from pre-reward M3 structural quota selection",
        "config_freeze_sha256": sha256_file(freeze_path),
    }
    write_json(parent / "DATA_MANIFEST.json", data_manifest)

    environment = read_json(parent / "environment_manifest.json")
    for seed in freeze["seeds"]:
        seed = int(seed)
        seed_dir = parent / f"seed_{seed}"
        config = {
            "schema_version": "vaguehydro_r.m4_seed_config.v1",
            "seed": seed,
            "parent_freeze": str(freeze_path.relative_to(root)),
            "base_model": freeze["base_model"],
            "sft_adapter": freeze["initial_sft_adapter"],
            "tool_registry": "hydro_remote_agent/configs/tool_registry.yaml",
            "m1_manifest": "runs/hydro_remote_agent/vaguehydro_r_m1_v1/rl_data_manifest.json",
            "m1_preservation_files": [
                "runs/hydro_remote_agent/vaguehydro_r_m1_v1/M1_REPORT.md",
                "runs/hydro_remote_agent/vaguehydro_r_m1_v1/EXPERIMENT_AUDIT.md",
                "runs/hydro_remote_agent/vaguehydro_r_m1_v1/rl_data_manifest.json",
                "runs/hydro_remote_agent/vaguehydro_r_m1_v1/rollout_smoke_summary.json",
            ],
            "train": "hydro_remote_agent/data/vague_hydro_sft_v2/train_curriculum_16360.jsonl",
            "valid": "hydro_remote_agent/data/vague_hydro_sft_v2/val_sft.jsonl",
            "frozen_test": "runs/hydro_remote_agent/agent_eval_v1/gold_240.jsonl",
            "output_dir": str(seed_dir.relative_to(root)).replace("\\", "/"),
            "environment_pins": {"trl": freeze["environment"]["trl"], "datasets": freeze["environment"]["datasets"]},
            "data": {
                "split": "train",
                "unique_prompt_samples": len(sample_ids),
                "selection_mode": "explicit_ids",
                "sample_ids": sample_ids,
                "max_image_pixels": freeze["data"]["max_image_pixels"],
                "image_resize_enforcement": freeze["data"]["image_resize_enforcement"],
            },
            "grpo": {
                "max_steps": freeze["training"]["max_optimizer_steps"],
                "per_device_train_batch_size": freeze["training"]["per_device_train_batch_size"],
                "gradient_accumulation_steps": freeze["training"]["gradient_accumulation_steps"],
                "generation_batch_size": freeze["training"]["generation_batch_size"],
                "num_generations": freeze["sampling"]["group_size"],
                "max_prompt_length": freeze["sampling"]["max_prompt_length"],
                "max_completion_length": freeze["sampling"]["max_new_tokens"],
                "max_new_tokens": freeze["sampling"]["max_new_tokens"],
                "do_sample": freeze["sampling"]["do_sample"],
                "temperature": freeze["sampling"]["temperature"],
                "top_p": freeze["sampling"]["top_p"],
                "learning_rate": freeze["training"]["learning_rate"],
                "beta": freeze["training"]["beta"],
                "epsilon": freeze["training"]["epsilon"],
                "loss_type": freeze["training"]["loss_type"],
                "scale_rewards": freeze["training"]["scale_rewards"],
                "gradient_checkpointing": freeze["training"]["gradient_checkpointing"],
                "optimizer": freeze["training"]["optimizer"],
                "save_total_limit": freeze["training"]["save_total_limit"],
                "generation_mode": "native_policy_sampling",
                "record_all_policy_samples": True,
                "stop_on_complete_json": bool(freeze["sampling"].get("stop_on_complete_json", False)),
                "json_termination_mode": freeze["sampling"].get("json_termination_mode", "disabled"),
                "schema_constrained_generation": bool(
                    freeze["sampling"].get("schema_constrained_generation", False)
                ),
                "constraint_max_allowed_tokens": int(
                    freeze["sampling"].get("constraint_max_allowed_tokens", 256)
                ),
                "constraint_scan_top_tokens": int(
                    freeze["sampling"].get("constraint_scan_top_tokens", 8192)
                ),
            },
            "reward_weights": deepcopy(freeze["reward_weights"]),
            "constraints": {
                "call_real_experts": False,
                "call_verifier": False,
                "exclude_frozen_test_ids": True,
                "allow_long_training": False,
                "single_gpu": True,
                "policy_samples": True,
                "forced_completions": False,
                "reward_modification": False,
                "result_based_candidate_filtering": False,
            },
        }
        write_json(seed_dir / "SEED_CONFIG.json", config)
        write_json(seed_dir / "environment_manifest.json", environment)
        command = (
            "cd /workspace/HydroGuardian && "
            "PYTHONPATH=/workspace/HydroGuardian "
            "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True CUDA_VISIBLE_DEVICES=0 "
            "python "
            "hydro_remote_agent/tools/train_vaguehydro_r_m2_grpo_smoke.py "
            "--project-root /workspace/HydroGuardian "
            f"--config {config['output_dir']}/SEED_CONFIG.json\n"
        )
        (seed_dir / "TRAIN_COMMAND.txt").write_text(command, encoding="utf-8")
    print(f"Prepared {len(freeze['seeds'])} frozen seed configs in {parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
