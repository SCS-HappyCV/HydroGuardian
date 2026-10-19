"""Formal v2 protocol components for VagueHydro Gold-Action GRPO.

This entrypoint deliberately supports preflight and resume simulation before
launching a real trainer. The actual trainer launch is gated by the formal
preflight report and must receive a completed validation/eval contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _json_default(value: Any) -> Any:
    if hasattr(value, "detach") and hasattr(value, "cpu"):
        tensor = value.detach().cpu()
        return {"__tensor__": True, "dtype": str(tensor.dtype), "shape": list(tensor.shape), "sha256": hashlib.sha256(tensor.numpy().tobytes()).hexdigest()}
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def _fsync_file(path: Path) -> None:
    with path.open("rb+") as handle:
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        # Windows does not expose directory handles with fsync semantics.
        # File contents are still fsynced before rename; directory durability
        # is provided by the atomic rename on the target filesystem.
        return
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def build_validation_manifest(
    valid_path: Path,
    frozen_path: Path,
    output_path: Path,
    *,
    limit: int = 64,
) -> dict[str, Any]:
    frozen_ids = {
        str(json.loads(line)["id"])
        for line in frozen_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    rows = []
    for line_number, line in enumerate(valid_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        identifier = str(record.get("id"))
        if identifier in frozen_ids:
            raise ValueError(f"validation record overlaps frozen test: {identifier}")
        rows.append({"id": identifier, "source_line": line_number})
        if len(rows) >= limit:
            break
    if not rows:
        raise ValueError("validation manifest is empty")
    result = {
        "schema_version": "vaguehydro.formal_validation_manifest.v2",
        "source_split": "valid",
        "selection": "first_non_frozen_records_in_source_order",
        "source_path": str(valid_path),
        "source_bytes": valid_path.stat().st_size,
        "source_sha256": sha256_file(valid_path),
        "frozen_path": str(frozen_path),
        "frozen_sha256": sha256_file(frozen_path),
        "frozen_overlap_ids": [],
        "record_count": len(rows),
        "records": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


@dataclass(frozen=True)
class ResumeIdentity:
    seed: int
    config_hash: str
    data_manifest_hash: str
    reward_hash: str


class AtomicCheckpointManager:
    """Write and select only fully committed same-seed checkpoints."""

    COMPLETED = "COMPLETED"

    def __init__(self, root: Path, identity: ResumeIdentity) -> None:
        self.root = root
        self.identity = identity
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, step: int, state: Mapping[str, Any]) -> Path:
        final = self.root / f"checkpoint-{int(step)}"
        if final.exists():
            raise FileExistsError(f"refusing to overwrite checkpoint: {final}")
        temp = self.root / f".checkpoint-{int(step)}.tmp-{os.getpid()}"
        if temp.exists():
            shutil.rmtree(temp)
        temp.mkdir(parents=True)
        metadata = {
            "schema_version": "vaguehydro.formal_atomic_checkpoint.v2",
            "step": int(step),
            "seed": self.identity.seed,
            "config_hash": self.identity.config_hash,
            "data_manifest_hash": self.identity.data_manifest_hash,
            "reward_hash": self.identity.reward_hash,
            "adapter_sha256": str(state["adapter_sha256"]),
            "optimizer_state": state["optimizer_state"],
            "scheduler_state": state["scheduler_state"],
            "trainer_state": state["trainer_state"],
            "rng_state": state["rng_state"],
        }
        (temp / "checkpoint.json").write_text(json.dumps(metadata, sort_keys=True, indent=2, default=_json_default) + "\n", encoding="utf-8")
        (temp / "adapter_model.safetensors").write_bytes(bytes.fromhex(str(state["adapter_hex"])))
        (temp / "optimizer.pt").write_bytes(bytes.fromhex(str(state["optimizer_hex"])))
        (temp / "scheduler.pt").write_bytes(bytes.fromhex(str(state["scheduler_hex"])))
        (temp / "trainer_state.json").write_text(json.dumps(state["trainer_state"], sort_keys=True) + "\n", encoding="utf-8")
        (temp / "step.marker").write_text(str(step) + "\n", encoding="ascii")
        for child in temp.iterdir():
            _fsync_file(child)
        _fsync_dir(temp)
        os.replace(temp, final)
        _fsync_dir(self.root)
        (final / self.COMPLETED).write_text("completed\n", encoding="ascii")
        _fsync_file(final / self.COMPLETED)
        _fsync_dir(final)
        _fsync_dir(self.root)
        return final

    def load_resume(self, checkpoint: Path) -> dict[str, Any]:
        checkpoint = checkpoint.resolve()
        if not (checkpoint / self.COMPLETED).is_file():
            raise ValueError("checkpoint is not committed")
        metadata = json.loads((checkpoint / "checkpoint.json").read_text(encoding="utf-8"))
        expected = self.identity.__dict__
        actual = {key: metadata.get(key) for key in expected}
        if actual != expected:
            raise ValueError(f"resume identity mismatch: expected={expected} actual={actual}")
        marker = int((checkpoint / "step.marker").read_text().strip())
        if marker != int(metadata["step"]):
            raise ValueError("step marker mismatch")
        return metadata


def validation_eval_contract() -> dict[str, Any]:
    """Machine-readable contract used by the future GRPO integration."""
    return {
        "eval_dataset": "validation_manifest",
        "eval_steps": 10,
        "eval_only": True,
        "gradient_updates": False,
        "reward_weight_updates": False,
        "sampling_parameter_updates": False,
        "early_stopping": False,
        "logged_components": ["schema", "action", "tool", "argument", "workflow", "stop"],
    }


def build_eval_training_kwargs(eval_dataset: Any) -> dict[str, Any]:
    """Return the only allowed trainer evaluation wiring for formal v2."""
    if eval_dataset is None:
        raise ValueError("formal validation requires a non-null eval_dataset")
    contract = validation_eval_contract()
    return {
        "eval_dataset": eval_dataset,
        "eval_strategy": "steps",
        "eval_steps": contract["eval_steps"],
        "metric_for_best_model": None,
        "load_best_model_at_end": False,
    }


def run_resume_simulation(output: Path) -> dict[str, Any]:
    identity = ResumeIdentity(7, "config", "data", "reward")
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        manager = AtomicCheckpointManager(Path(tmp), identity)
        state = {
            "adapter_sha256": "adapter-step-3",
            "adapter_hex": "616263",
            "optimizer_hex": "646566",
            "scheduler_hex": "676869",
            "optimizer_state": {"step": 3, "exp_avg": [1, 2]},
            "scheduler_state": {"last_epoch": 3},
            "trainer_state": {"global_step": 3},
            "rng_state": {"python": random.getstate()[1][:3]},
        }
        checkpoint = manager.write(3, state)
        loaded = manager.load_resume(checkpoint)
        incomplete = Path(tmp) / "checkpoint-4"
        incomplete.mkdir()
        (incomplete / "checkpoint.json").write_text(json.dumps({"step": 4}), encoding="utf-8")
        try:
            manager.load_resume(incomplete)
        except ValueError:
            incomplete_rejected = True
        else:
            incomplete_rejected = False
        return {
            "status": "pass" if loaded["step"] == 3 and incomplete_rejected else "fail",
            "restored_global_step": loaded["trainer_state"]["global_step"],
            "optimizer_state_restored": loaded["optimizer_state"],
            "scheduler_state_restored": loaded["scheduler_state"],
            "rng_state_restored": loaded["rng_state"],
            "adapter_sha256_restored": loaded["adapter_sha256"],
            "incomplete_checkpoint_rejected": incomplete_rejected,
            "no_duplicate_step": loaded["step"] == 3,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["resume-test", "validation-manifest"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--valid", type=Path)
    parser.add_argument("--frozen", type=Path)
    args = parser.parse_args()
    if args.mode == "resume-test":
        args.output.mkdir(parents=True, exist_ok=True)
        result = run_resume_simulation(args.output)
        (args.output / "RESUME_SIMULATION_REPORT.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(result["status"])
        return 0 if result["status"] == "pass" else 2
    if args.valid is None or args.frozen is None:
        parser.error("validation-manifest requires --valid and --frozen")
    result = build_validation_manifest(args.valid, args.frozen, args.output)
    print(json.dumps({"status": "pass", "record_count": result["record_count"], "sha256": result["source_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
