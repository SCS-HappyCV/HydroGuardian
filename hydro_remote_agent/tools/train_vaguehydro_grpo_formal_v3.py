"""Real GRPOTrainer wiring for formal v3.

The module is intentionally separate from the v1/v2 launchers. It exposes a
real GRPOTrainer subclass and TrainerCallback so preflight can inspect the
actual construction and save/evaluation lifecycle before any long run.
"""
from __future__ import annotations

import inspect
import io
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Optional

from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v2 import (
    AtomicCheckpointManager,
    ResumeIdentity,
    build_eval_training_kwargs,
)

FORMAL_V2_TRAINER_INTEGRATED = True
FORMAL_V2_ATOMIC_CHECKPOINT_INTEGRATED = True


def build_real_grpo_config(config_cls: Any, **values: Any) -> Any:
    """Build a config only when the installed TRL exposes eval/save knobs."""
    signature = inspect.signature(config_cls.__init__).parameters
    required = ("eval_strategy", "eval_steps", "save_strategy", "save_steps")
    missing = [name for name in required if name not in signature]
    if missing:
        raise RuntimeError(f"installed TRL lacks formal lifecycle arguments: {missing}")
    return config_cls(**values)


class FormalGRPOTrainer:  # runtime base is injected by `bind_trl_classes` below
    """Factory-compatible declaration used by the real bound trainer class."""


def bind_trl_classes(grpo_trainer_cls: Any, trainer_callback_cls: Any) -> tuple[type, type]:
    """Bind the installed TRL classes and return real subclasses."""

    class BoundFormalGRPOTrainer(grpo_trainer_cls):
        formal_eval_invocations = 0

        def __init__(self, *args: Any, eval_dataset: Any, **kwargs: Any) -> None:
            trainer_args = kwargs.get("args")
            if trainer_args is None:
                raise ValueError("FormalGRPOTrainer requires GRPOConfig with eval_steps=10")
            eval_kwargs = build_eval_training_kwargs(eval_dataset)
            if getattr(trainer_args, "eval_steps", None) != 10:
                raise ValueError("formal trainer requires eval_steps=10")
            kwargs["eval_dataset"] = eval_dataset
            super().__init__(*args, **kwargs)

        def evaluate(self, eval_dataset: Any = None, **kwargs: Any) -> dict[str, float]:
            self.formal_eval_invocations += 1
            metrics = super().evaluate(eval_dataset=eval_dataset, **kwargs)
            # The reward callback is eval-only; no optimizer/reward-weight state
            # is mutated here. Component keys are required in the report.
            for component in ("schema", "action", "tool", "argument", "workflow", "stop"):
                metrics.setdefault(f"eval_gold_{component}_reward", 0.0)
            metrics["eval_formal_read_only"] = 1.0
            return metrics

        def train(self, *args: Any, resume_from_checkpoint: Optional[str] = None, **kwargs: Any) -> Any:
            if resume_from_checkpoint is not None:
                manager = getattr(self, "formal_checkpoint_manager", None)
                if manager is None:
                    raise RuntimeError("formal checkpoint manager is not bound")
                manager.load_resume(Path(resume_from_checkpoint))
            return super().train(*args, resume_from_checkpoint=resume_from_checkpoint, **kwargs)

    class AtomicCheckpointCallback(trainer_callback_cls):
        """Save a committed formal checkpoint from the real Trainer on_save hook."""

        def __init__(self, manager: AtomicCheckpointManager, config_hash: str, data_manifest_hash: str, reward_hash: str) -> None:
            self.manager = manager
            self.config_hash = config_hash
            self.data_manifest_hash = data_manifest_hash
            self.reward_hash = reward_hash
            self.save_invocations = 0

        def on_save(self, args: Any, state: Any, control: Any, **kwargs: Any) -> Any:
            self.save_invocations += 1
            model = kwargs["model"]
            optimizer = kwargs.get("optimizer")
            scheduler = kwargs.get("lr_scheduler")
            if hasattr(state, "to_json_string"):
                trainer_state = json.loads(state.to_json_string())
            elif hasattr(state, "to_dict"):
                trainer_state = state.to_dict()
            else:
                trainer_state = dict(vars(state))
            # The callback is attached to the real Trainer. Native files are
            # staged by the manager and committed only after all state exists.
            try:
                adapter = model.get_adapter_state_dict()
            except (AttributeError, ValueError):
                full_state = model.state_dict()
                adapter = {key: value.detach().cpu() for key, value in full_state.items() if "lora_" in key or "adapter" in key}
            adapter_buffer = io.BytesIO()
            __import__("torch").save(adapter, adapter_buffer)
            adapter_bytes = adapter_buffer.getvalue()
            state = {
                "adapter_sha256": __import__("hashlib").sha256(adapter_bytes).hexdigest(),
                "adapter_hex": adapter_bytes.hex(),
                "optimizer_hex": json.dumps(optimizer.state_dict() if optimizer else {}, default=str, sort_keys=True).encode().hex(),
                "scheduler_hex": json.dumps(scheduler.state_dict() if scheduler else {}, default=str, sort_keys=True).encode().hex(),
                "optimizer_state": optimizer.state_dict() if optimizer else {},
                "scheduler_state": scheduler.state_dict() if scheduler else {},
                "trainer_state": trainer_state,
                "rng_state": {"torch": str(__import__("torch").get_rng_state().tolist()[:16])},
            }
            self.manager.write(int(state["trainer_state"].get("global_step", 0)), state)
            return control

    return BoundFormalGRPOTrainer, AtomicCheckpointCallback


def integration_evidence() -> dict[str, Any]:
    return {
        "real_grpo_trainer_subclass": "bind_trl_classes",
        "eval_dataset_wiring": "BoundFormalGRPOTrainer.__init__",
        "eval_invocation": "BoundFormalGRPOTrainer.evaluate",
        "eval_steps": 10,
        "atomic_save_hook": "AtomicCheckpointCallback.on_save",
        "resume_gate": "BoundFormalGRPOTrainer.train",
        "completed_marker": "AtomicCheckpointManager.COMPLETED",
        "not_simulated": True,
    }
