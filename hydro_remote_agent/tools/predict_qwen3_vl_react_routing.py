from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json, iter_batches, read_jsonl
from hydro_remote_agent.baselines.react_planner import react_draft_messages, react_final_messages


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the two-round ReAct-style Qwen3-VL baseline.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--draft-max-new-tokens", type=int, default=384)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--max-image-pixels", type=int, default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--image-source-root", default=None)
    parser.add_argument("--image-cache-root", default=None)
    parser.add_argument("--resume", action="store_true")
    return parser


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
                    block["image"] = target + image_path[len(source):]


def _generate(model: Any, processor: Any, conversations: Sequence[List[Dict[str, Any]]],
              max_new_tokens: int) -> tuple[List[str], List[int], float]:
    import torch

    inputs = processor.apply_chat_template(
        conversations, tokenize=True, add_generation_prompt=True, padding=True,
        return_dict=True, return_tensors="pt",
    ).to("cuda")
    started = time.perf_counter()
    with torch.inference_mode():
        generated = model.generate(**inputs, max_new_tokens=max(max_new_tokens, 1), do_sample=False)
    elapsed = time.perf_counter() - started
    trimmed = generated[:, inputs["input_ids"].shape[1]:]
    token_counts = [
        int((tokens != processor.tokenizer.pad_token_id).sum().item()) for tokens in trimmed
    ]
    outputs = processor.batch_decode(
        trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False,
    )
    return [output.strip() for output in outputs], token_counts, elapsed


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.batch_size <= 0:
        raise ValueError("batch_size must be positive")
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    records = read_jsonl(Path(args.input))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = set()
    if args.resume and output_path.exists():
        completed = {str(row["id"]) for row in read_jsonl(output_path)}
    pending = [record for record in records if str(record["id"]) not in completed]
    if not pending:
        print(f"QWEN3_VL_REACT_ROUTING_OK records={len(records)} output={output_path}")
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
        model_path, dtype=dtype, device_map={"": 0}, attn_implementation="sdpa",
        local_files_only=True, trust_remote_code=bool(config.get("trust_remote_code", False)),
    ).eval()
    print(f"REACT_BACKBONE_LOADED seconds={time.perf_counter() - load_started:.2f}", flush=True)

    mode = "a" if args.resume and output_path.exists() else "w"
    completed_count = len(completed)
    with output_path.open(mode, encoding="utf-8", newline="\n") as handle:
        for batch_index, batch in enumerate(iter_batches(pending, args.batch_size), start=1):
            draft_conversations = [react_draft_messages(record) for record in batch]
            _rewrite_image_paths(draft_conversations, args.image_source_root, args.image_cache_root)
            drafts, draft_tokens, draft_seconds = _generate(
                model, processor, draft_conversations, args.draft_max_new_tokens
            )
            final_conversations = [
                react_final_messages(record, draft) for record, draft in zip(batch, drafts)
            ]
            _rewrite_image_paths(final_conversations, args.image_source_root, args.image_cache_root)
            finals, final_tokens, final_seconds = _generate(
                model, processor, final_conversations, args.max_new_tokens
            )
            for record, draft, final, draft_count, final_count in zip(
                batch, drafts, finals, draft_tokens, final_tokens
            ):
                handle.write(canonical_json({
                    "id": str(record["id"]),
                    "prediction": final,
                    "inference": {
                        "baseline": "qwen3_vl_react_style",
                        "planner_rounds": 2,
                        "draft": draft,
                        "draft_generated_tokens": draft_count,
                        "final_generated_tokens": final_count,
                        "batch_size": len(batch),
                        "draft_batch_seconds": draft_seconds,
                        "final_batch_seconds": final_seconds,
                        "total_batch_seconds": draft_seconds + final_seconds,
                        "model_id": config["model_id"],
                        "revision": config["revision"],
                        "max_image_pixels": int(args.max_image_pixels or config.get("max_image_pixels", 1024 * 1024)),
                    },
                }) + "\n")
                handle.flush()
            completed_count += len(batch)
            print(
                f"REACT_BATCH_OK index={batch_index} completed={completed_count} "
                f"draft_seconds={draft_seconds:.2f} final_seconds={final_seconds:.2f} "
                f"generated_tokens={sum(draft_tokens) + sum(final_tokens)}",
                flush=True,
            )
    print(f"QWEN3_VL_REACT_ROUTING_OK records={len(records)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
