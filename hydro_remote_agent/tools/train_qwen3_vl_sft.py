from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

import torch

from hydro_remote_agent.training.qwen3_vl_sft import (
    JsonlOffsetDataset,
    Qwen3VLSFTCollator,
    SFT_TARGET_FORMATS,
    load_training_config,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the Qwen3-VL VagueHydro Planner with LoRA.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--max-train-samples", type=int, default=None)
    parser.add_argument("--max-eval-samples", type=int, default=None)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=None)
    parser.add_argument("--per-device-train-batch-size", type=int, default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--resume-from-checkpoint", default=None)
    parser.add_argument("--init-adapter", default=None)
    parser.add_argument("--target-format", choices=SFT_TARGET_FORMATS, default=None)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_training_config(args.config)
    backbone = json.loads(Path(config["backbone_config"]).read_text(encoding="utf-8"))

    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration, Trainer, TrainingArguments

    configured_cache = config.get("runtime", {}).get("model_cache_path")
    model_path = args.model_path or (
        configured_cache if configured_cache and Path(configured_cache).is_dir() else backbone["local_path"]
    )
    processor = AutoProcessor.from_pretrained(
        model_path,
        max_pixels=int(config["data"]["max_image_pixels"]),
        local_files_only=True,
    )
    processor.tokenizer.padding_side = "right"
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_path,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        local_files_only=True,
        low_cpu_mem_usage=True,
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable(
        gradient_checkpointing_kwargs={"use_reentrant": False}
    )
    model.enable_input_require_grads()
    if args.init_adapter:
        model = PeftModel.from_pretrained(model, args.init_adapter, is_trainable=True)
    else:
        lora = config["lora"]
        model = get_peft_model(
            model,
            LoraConfig(
                r=int(lora["rank"]),
                lora_alpha=int(lora["alpha"]),
                lora_dropout=float(lora["dropout"]),
                bias="none",
                task_type="CAUSAL_LM",
                target_modules=list(lora["target_modules"]),
            ),
        )
    model.print_trainable_parameters()

    data = config["data"]
    target_format = args.target_format or str(data.get("target_format", "agent_request"))
    train_dataset = JsonlOffsetDataset(
        data["train_file"],
        max_samples=args.max_train_samples,
    )
    eval_dataset = JsonlOffsetDataset(
        data["eval_file"],
        max_samples=args.max_eval_samples or int(data["max_eval_samples"]),
    )
    training = dict(config["training"])
    if args.max_steps is not None:
        training["max_steps"] = args.max_steps
    if args.gradient_accumulation_steps is not None:
        training["gradient_accumulation_steps"] = args.gradient_accumulation_steps
    if args.per_device_train_batch_size is not None:
        training["per_device_train_batch_size"] = args.per_device_train_batch_size
    output_dir = args.output_dir or config["output_dir"]
    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=int(training["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(training["per_device_eval_batch_size"]),
        gradient_accumulation_steps=int(training["gradient_accumulation_steps"]),
        learning_rate=float(training["learning_rate"]),
        num_train_epochs=float(training["num_train_epochs"]),
        max_steps=int(training.get("max_steps", -1)),
        warmup_ratio=float(training["warmup_ratio"]),
        lr_scheduler_type=str(training["lr_scheduler_type"]),
        weight_decay=float(training["weight_decay"]),
        max_grad_norm=float(training["max_grad_norm"]),
        bf16=True,
        tf32=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=int(training["logging_steps"]),
        eval_strategy=str(training["eval_strategy"]),
        eval_steps=int(training["eval_steps"]),
        save_strategy="steps",
        save_steps=int(training["save_steps"]),
        save_total_limit=int(training["save_total_limit"]),
        dataloader_num_workers=int(training["dataloader_num_workers"]),
        remove_unused_columns=False,
        report_to="none",
        optim="adamw_torch_fused",
        seed=int(training["seed"]),
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=Qwen3VLSFTCollator(
            processor=processor,
            max_length=int(data["max_length"]),
            image_source_root=data.get("image_source_root"),
            image_cache_root=data.get("image_cache_root"),
            target_format=target_format,
        ),
    )
    resume_checkpoint = args.resume_from_checkpoint or training.get("resume_from_checkpoint")
    if resume_checkpoint == "latest":
        checkpoints = sorted(
            Path(output_dir).glob("checkpoint-*"),
            key=lambda path: int(path.name.split("-")[-1]),
        )
        resume_checkpoint = str(checkpoints[-1]) if checkpoints else None
    torch.cuda.reset_peak_memory_stats()
    result = trainer.train(resume_from_checkpoint=resume_checkpoint)
    result.metrics["peak_gpu_memory_gib"] = torch.cuda.max_memory_allocated() / (1024 ** 3)
    result.metrics["trainable_parameter_count"] = sum(
        parameter.numel() for parameter in model.parameters() if parameter.requires_grad
    )
    trainer.save_model(output_dir)
    processor.save_pretrained(output_dir)
    trainer.save_metrics("train", result.metrics)
    print(
        f"QWEN3_VL_SFT_OK output={output_dir} "
        f"peak_gpu_gib={result.metrics['peak_gpu_memory_gib']:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
