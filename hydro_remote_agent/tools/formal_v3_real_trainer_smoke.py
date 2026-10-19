"""One real GRPOTrainer smoke; deliberately separate from formal 100-step launch."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    import torch
    from datasets import Dataset
    from peft import PeftModel
    from transformers import AutoProcessor, TrainerCallback, Qwen3VLForConditionalGeneration
    from trl import GRPOConfig, GRPOTrainer

    try:
        from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v2 import AtomicCheckpointManager, ResumeIdentity
    except ModuleNotFoundError:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v2 import AtomicCheckpointManager, ResumeIdentity
    from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v3 import bind_trl_classes, build_real_grpo_config

    root = args.project_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    base = "/models/Qwen3-VL-8B-Instruct"
    adapter = root / "runs/hydro_remote_agent/qwen3_vl_8b_lora_v1"
    processor = AutoProcessor.from_pretrained(base, local_files_only=True)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        base, dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True, low_cpu_mem_usage=True
    )
    model = PeftModel.from_pretrained(model, adapter, is_trainable=True)
    train = Dataset.from_list([{"prompt": "Return a short JSON object.", "id": "smoke-train"}])
    valid = Dataset.from_list([{"prompt": "Return a short JSON object.", "id": "smoke-valid"}])

    BoundTrainer, Callback = bind_trl_classes(GRPOTrainer, TrainerCallback)
    config = build_real_grpo_config(
        GRPOConfig,
        output_dir=str(output / "native_trainer"),
        max_steps=10,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        num_generations=2,
        generation_batch_size=2,
        max_prompt_length=128,
        max_completion_length=8,
        temperature=1.0,
        top_p=0.9,
        learning_rate=1e-6,
        beta=0.0,
        logging_strategy="steps",
        logging_steps=1,
        eval_strategy="steps",
        eval_steps=10,
        save_strategy="steps",
        save_steps=10,
        save_total_limit=1,
        remove_unused_columns=False,
        report_to="none",
        bf16=True,
        use_vllm=False,
    )
    reward_funcs = []
    for component in ("schema", "action", "tool", "argument", "workflow", "stop"):
        def reward_func(completions, _component=component, **kwargs):
            return [1.0 for _ in completions]
        reward_func.__name__ = f"gold_{component}_reward"
        reward_funcs.append(reward_func)

    trainer = BoundTrainer(
        model=model,
        reward_funcs=reward_funcs,
        args=config,
        train_dataset=train,
        eval_dataset=valid,
        processing_class=processor,
    )
    manager = AtomicCheckpointManager(output / "atomic_checkpoints", ResumeIdentity(0, "smoke", "smoke", "smoke"))
    trainer.formal_checkpoint_manager = manager
    callback = Callback(manager, "smoke", "smoke", "smoke")
    trainer.add_callback(callback)
    result = trainer.train()
    report = {
        "status": "pass" if trainer.formal_eval_invocations >= 1 and callback.save_invocations >= 1 else "blocked",
        "global_step": trainer.state.global_step,
        "formal_eval_invocations": trainer.formal_eval_invocations,
        "atomic_save_invocations": callback.save_invocations,
        "trainer_log_history": trainer.state.log_history,
        "train_result": str(result),
    }
    (output / "REAL_TRAINER_SMOKE_REPORT.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "global_step", "formal_eval_invocations", "atomic_save_invocations")}))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
