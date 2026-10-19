from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import (
    PLANNER_PROMPT_PROFILES,
    canonical_json,
    iter_batches,
    planner_messages,
    read_jsonl,
    stratified_sample,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run zero-shot Qwen3-VL Agent routing.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sample-manifest", required=True)
    parser.add_argument("--sample-count", type=int, default=24)
    parser.add_argument("--seed", type=int, default=20260731)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--max-image-pixels", type=int, default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--adapter-path", default=None)
    parser.add_argument("--merge-adapter", action="store_true")
    parser.add_argument("--image-source-root", default=None)
    parser.add_argument("--image-cache-root", default=None)
    parser.add_argument("--no-resample", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--prompt-profile",
        choices=PLANNER_PROMPT_PROFILES,
        default="full",
    )
    return parser


def _load_completed(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    return {str(row["id"]): row for row in read_jsonl(path)}


def _rewrite_image_paths(
    conversations: Sequence[List[Dict[str, Any]]],
    source_root: Optional[str],
    cache_root: Optional[str],
) -> None:
    if not source_root or not cache_root:
        return
    source = source_root.rstrip("/\\")
    target = cache_root.rstrip("/\\")
    for conversation in conversations:
        for message in conversation:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                image_path = block.get("image") if isinstance(block, dict) else None
                if isinstance(image_path, str) and (
                    image_path == source or image_path.startswith(source + "/")
                ):
                    block["image"] = target + image_path[len(source) :]


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    input_records = read_jsonl(Path(args.input))
    if args.no_resample:
        records = input_records
        if args.sample_count not in (0, len(records)):
            raise ValueError(
                f"frozen manifest contains {len(records)} records, not {args.sample_count}"
            )
    else:
        records = stratified_sample(
            input_records,
            count=max(args.sample_count, 0),
            seed=args.seed,
        )
    manifest_path = Path(args.sample_manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "".join(canonical_json(record) + "\n" for record in records),
        encoding="utf-8",
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = _load_completed(output_path) if args.resume else {}
    pending = [record for record in records if str(record["id"]) not in completed]
    if not pending:
        print(f"QWEN3_VL_ROUTING_PREDICT_OK records={len(records)} output={output_path}")
        return 0

    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    model_path = str(args.model_path or config["local_path"])
    processor = AutoProcessor.from_pretrained(
        model_path,
        max_pixels=int(args.max_image_pixels or config.get("max_image_pixels", 1024 * 1024)),
        local_files_only=True,
        trust_remote_code=bool(config.get("trust_remote_code", False)),
    )
    processor.tokenizer.padding_side = "left"
    dtype = torch.bfloat16 if config.get("dtype") == "bfloat16" else torch.float16
    load_started = time.perf_counter()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_path,
        dtype=dtype,
        device_map={"": 0},
        attn_implementation="sdpa",
        local_files_only=True,
        trust_remote_code=bool(config.get("trust_remote_code", False)),
    )
    if args.adapter_path:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, args.adapter_path)
        if args.merge_adapter:
            model = model.merge_and_unload()
    model = model.eval()
    print(f"BACKBONE_LOADED seconds={time.perf_counter() - load_started:.2f}", flush=True)

    mode = "a" if args.resume and output_path.exists() else "w"
    completed_count = len(completed)
    with output_path.open(mode, encoding="utf-8", newline="\n") as handle:
        for batch_index, batch in enumerate(iter_batches(pending, args.batch_size), start=1):
            conversations = [
                planner_messages(record, prompt_profile=args.prompt_profile) for record in batch
            ]
            _rewrite_image_paths(
                conversations,
                args.image_source_root,
                args.image_cache_root,
            )
            inputs = processor.apply_chat_template(
                conversations,
                tokenize=True,
                add_generation_prompt=True,
                padding=True,
                return_dict=True,
                return_tensors="pt",
            ).to("cuda")
            started = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(
                    **inputs,
                    max_new_tokens=max(args.max_new_tokens, 1),
                    do_sample=False,
                )
            elapsed = time.perf_counter() - started
            trimmed = generated[:, inputs["input_ids"].shape[1] :]
            generated_token_counts = [
                int((tokens != processor.tokenizer.pad_token_id).sum().item())
                for tokens in trimmed
            ]
            outputs = processor.batch_decode(
                trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            for record, prediction, token_count in zip(batch, outputs, generated_token_counts):
                row = {
                    "id": str(record["id"]),
                    "prediction": prediction.strip(),
                    "inference": {
                        "batch_index": batch_index,
                        "batch_size": len(batch),
                        "batch_seconds": elapsed,
                        "model_id": config["model_id"],
                        "revision": config["revision"],
                        "adapter_path": args.adapter_path,
                        "generated_tokens": token_count,
                        "max_image_pixels": int(
                            args.max_image_pixels
                            or config.get("max_image_pixels", 1024 * 1024)
                        ),
                        "prompt_profile": args.prompt_profile,
                    },
                }
                handle.write(canonical_json(row) + "\n")
                handle.flush()
            completed_count += len(batch)
            print(
                f"BATCH_OK index={batch_index} completed={completed_count} "
                f"seconds={elapsed:.2f} generated_tokens={sum(generated_token_counts)} "
                f"peak_gpu_gib={torch.cuda.max_memory_allocated() / (1024 ** 3):.2f}",
                flush=True,
            )
    print(f"QWEN3_VL_ROUTING_PREDICT_OK records={len(records)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
