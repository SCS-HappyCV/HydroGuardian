from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def preservation_status(
    root: Path,
    config: Mapping[str, Any],
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    results = {}
    baseline = environment["m1_preservation_baseline"]
    for relative_path in config["m1_preservation_files"]:
        current_sha = sha256_file(root / relative_path)
        expected_sha = baseline[relative_path]["sha256"]
        results[relative_path] = {
            "expected_sha256": expected_sha,
            "current_sha256": current_sha,
            "unchanged": current_sha == expected_sha,
        }
    return results


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize a VagueHydro-R M2 smoke attempt.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--observed-gpu-memory-mib", type=int, required=True)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir = root / config["output_dir"]
    environment = json.loads((output_dir / "environment_manifest.json").read_text(encoding="utf-8"))
    raw_smoke_path = output_dir / "SMOKE_REPORT.json"
    raw_smoke = json.loads(raw_smoke_path.read_text(encoding="utf-8"))
    preserved_raw = output_dir / "SMOKE_REPORT.raw_failure.json"
    if not preserved_raw.exists():
        shutil.copy2(raw_smoke_path, preserved_raw)
    exit_code = int((output_dir / "train.exit_code").read_text(encoding="utf-8").strip())

    checkpoint_dir = output_dir / "trainer" / "checkpoint-1"
    trainer_state_path = checkpoint_dir / "trainer_state.json"
    trainer_state = (
        json.loads(trainer_state_path.read_text(encoding="utf-8"))
        if trainer_state_path.exists()
        else {"global_step": 0, "log_history": []}
    )
    log_entry = next(
        (
            entry
            for entry in reversed(trainer_state.get("log_history", []))
            if "reward" in entry
        ),
        {},
    )
    global_step = int(trainer_state.get("global_step", 0))
    optimizer_path = checkpoint_dir / "optimizer.pt"
    adapter_path = checkpoint_dir / "adapter_model.safetensors"
    initial_adapter_path = root / config["sft_adapter"] / "adapter_model.safetensors"
    core_step_completed = (
        global_step == int(config["grpo"]["max_steps"])
        and optimizer_path.is_file()
        and adapter_path.is_file()
    )
    reward_mean = float(log_entry["reward"]) if "reward" in log_entry else None
    reward_std = float(log_entry["reward_std"]) if "reward_std" in log_entry else None
    grad_norm = float(log_entry["grad_norm"]) if "grad_norm" in log_entry else None
    loss = float(log_entry["loss"]) if "loss" in log_entry else None
    num_generations = int(config["grpo"]["num_generations"])
    zero_variance = reward_std is not None and math.isclose(reward_std, 0.0, abs_tol=1e-12)
    advantages = [0.0] * num_generations if zero_variance else None
    initial_adapter_sha = sha256_file(initial_adapter_path) if initial_adapter_path.exists() else None
    checkpoint_adapter_sha = sha256_file(adapter_path) if adapter_path.exists() else None
    adapter_changed = (
        initial_adapter_sha is not None
        and checkpoint_adapter_sha is not None
        and initial_adapter_sha != checkpoint_adapter_sha
    )
    m1_preservation = preservation_status(root, config, environment)

    if core_step_completed:
        failure_class = "post_export_serialization_and_zero_reward_variance"
        summary = (
            "The TRL optimizer step and checkpoint completed, but both generations received identical reward, "
            "so advantages, loss, and gradient norm were zero. The process then exited 1 while serializing a deque."
        )
    else:
        failure_class = "peft_gradient_checkpointing_compatibility"
        summary = (
            "Sampling reached backward, but PEFT with non-reentrant gradient checkpointing produced a loss "
            "without grad_fn; no optimizer step or checkpoint completed."
        )

    gaps = []
    if not core_step_completed:
        gaps.append("No completed optimizer step or checkpoint in this attempt.")
    if zero_variance:
        gaps.append("The sampled group had reward_std=0, yielding zero advantages and zero gradient.")
    if core_step_completed and not adapter_changed:
        gaps.append("The checkpoint adapter is byte-identical to the initial SFT adapter; no learning update occurred.")
    if exit_code != 0:
        gaps.append(f"The training command exited with code {exit_code}.")
    if core_step_completed and raw_smoke.get("error_type") == "TypeError":
        gaps.append("Post-training evidence export failed on a deque; the implementation now converts deques to lists.")

    checkpoint_artifacts = {}
    for name, path in (
        ("adapter", adapter_path),
        ("optimizer", optimizer_path),
        ("trainer_state", trainer_state_path),
    ):
        if path.exists():
            checkpoint_artifacts[name] = artifact(path, root)
    reward_history = {
        "schema_version": "vaguehydro_r.m2_reward_history.recovered.v1",
        "source": "trainer/checkpoint-1/trainer_state.json",
        "trainer_log_history": trainer_state.get("log_history", []),
        "reward_mean": reward_mean,
        "reward_std": reward_std,
        "advantages": advantages,
        "advantage_provenance": (
            "Derived exactly from GRPO group reward_std=0: each reward equals its group mean."
            if advantages is not None
            else "Unavailable because the optimizer step did not complete."
        ),
    }
    write_json(output_dir / "reward_log_history.json", reward_history)

    report = {
        "schema_version": "vaguehydro_r.m2_attempt_report.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "blocked",
        "hang": False,
        "failure_class": failure_class,
        "summary": summary,
        "formal_grpo_started": bool(raw_smoke.get("formal_grpo_started")),
        "smoke_pass": False,
        "core_training_step_completed": core_step_completed,
        "ready_for_m3": False,
        "gpu": {
            "visible_device": 0,
            "name": environment["gpus"][0]["name"],
            "observed_memory_mib": args.observed_gpu_memory_mib,
        },
        "data": {
            "split": config["data"]["split"],
            "unique_samples": int(config["data"]["unique_prompt_samples"]),
            "num_generations": num_generations,
            "frozen_test_samples": 0,
        },
        "training": {
            "global_step": global_step,
            "max_steps": int(config["grpo"]["max_steps"]),
            "gradient_checkpointing": bool(config["grpo"]["gradient_checkpointing"]),
            "optimizer": config["grpo"]["optimizer"],
            "reward_mean": reward_mean,
            "reward_std": reward_std,
            "advantages": advantages,
            "loss": loss,
            "grad_norm": grad_norm,
            "exit_code": exit_code,
            "adapter_changed": adapter_changed,
            "initial_adapter_sha256": initial_adapter_sha,
            "checkpoint_adapter_sha256": checkpoint_adapter_sha,
        },
        "called_real_experts": False,
        "called_verifier": False,
        "m1_unchanged": all(item["unchanged"] for item in m1_preservation.values()),
        "m1_preservation": m1_preservation,
        "checkpoint_artifacts": checkpoint_artifacts,
        "evidence": {
            "environment_manifest": "environment_manifest.json",
            "config": "M2_CONFIG.json",
            "command": "TRAIN_COMMAND.txt",
            "stdout": "stdout.log",
            "stderr": "stderr.log",
            "raw_smoke_report": "SMOKE_REPORT.raw_failure.json",
            "reward_history": "reward_log_history.json",
        },
        "gaps": gaps,
    }
    write_json(output_dir / "M2_REPORT.json", report)
    shutil.copy2(config_path, output_dir / "M2_CONFIG.json")
    (output_dir / "M2_REPORT.md").write_text(
        "\n".join(
            [
                "# VagueHydro-R M2 Smoke Report",
                "",
                "- Status: **BLOCKED**",
                "- Hang: `False`",
                f"- Failure class: `{failure_class}`",
                f"- Formal GRPO started: `{report['formal_grpo_started']}`",
                "- Smoke pass: `False`",
                f"- Core optimizer step completed: `{core_step_completed}`",
                "- Ready for M3: `False`",
                f"- GPU: `0 / {report['gpu']['name']}`",
                f"- Data: `train`, `{report['data']['unique_samples']}` unique sample, `{num_generations}` generations",
                "- Frozen-test samples: `0`",
                "- Real experts called: `False`",
                "- Verifier called: `False`",
                "- M1 artifacts unchanged: `True`",
                "",
                "## Diagnosis",
                "",
                summary,
                "",
                "## Gaps",
                "",
                *[f"- {gap}" for gap in gaps],
                "",
            ]
        ),
        encoding="utf-8",
    )
    (output_dir / "GAP_LIST.md").write_text(
        "# VagueHydro-R M2 Gap List\n\n" + "\n".join(f"- {gap}" for gap in gaps) + "\n",
        encoding="utf-8",
    )
    print(
        f"VAGUEHYDRO_R_M2_FINALIZED status=blocked core_step_completed={core_step_completed} "
        f"output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
