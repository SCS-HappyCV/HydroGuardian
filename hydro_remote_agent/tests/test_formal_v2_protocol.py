import json
from pathlib import Path

from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v2 import (
    AtomicCheckpointManager,
    ResumeIdentity,
    build_eval_training_kwargs,
    run_resume_simulation,
    validation_eval_contract,
)


def test_eval_contract_is_read_only():
    contract = validation_eval_contract()
    assert contract["eval_steps"] == 10
    assert contract["eval_only"] is True
    assert contract["gradient_updates"] is False
    assert contract["reward_weight_updates"] is False
    assert contract["sampling_parameter_updates"] is False
    kwargs = build_eval_training_kwargs([{"id": "validation"}])
    assert kwargs["eval_dataset"]
    assert kwargs["eval_steps"] == 10
    assert kwargs["eval_strategy"] == "steps"
    assert kwargs["load_best_model_at_end"] is False


def test_atomic_resume_simulation(tmp_path: Path):
    result = run_resume_simulation(tmp_path)
    assert result["status"] == "pass"
    assert result["restored_global_step"] == 3
    assert result["optimizer_state_restored"]["step"] == 3
    assert result["scheduler_state_restored"]["last_epoch"] == 3
    assert result["incomplete_checkpoint_rejected"] is True
    assert result["no_duplicate_step"] is True


def test_resume_rejects_identity_mismatch(tmp_path: Path):
    manager = AtomicCheckpointManager(tmp_path, ResumeIdentity(1, "c", "d", "r"))
    state = {"adapter_sha256": "a", "adapter_hex": "61", "optimizer_hex": "62", "scheduler_hex": "63", "optimizer_state": {}, "scheduler_state": {}, "trainer_state": {"global_step": 1}, "rng_state": {}}
    checkpoint = manager.write(1, state)
    other = AtomicCheckpointManager(tmp_path, ResumeIdentity(2, "c", "d", "r"))
    try:
        other.load_resume(checkpoint)
    except ValueError as exc:
        assert "identity mismatch" in str(exc)
    else:
        raise AssertionError("identity mismatch was accepted")
