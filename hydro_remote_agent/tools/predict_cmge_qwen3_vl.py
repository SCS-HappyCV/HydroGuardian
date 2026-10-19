from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json, iter_batches, read_jsonl
from hydro_remote_agent.cmge_planner import (
    canonical_json as cmge_canonical_json,
    canonicalize_cmge_plan,
    cmge_planner_messages,
)
from hydro_remote_agent.evaluation.routing import parse_json_response
from hydro_remote_agent.tools.predict_qwen3_vl_routing import _rewrite_image_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Qwen3-VL CMGE claim-wise planning.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-new-tokens", type=int, default=1536)
    parser.add_argument("--max-image-pixels", type=int, default=None)
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--adapter-path", default=None)
    parser.add_argument("--merge-adapter", action="store_true")
    parser.add_argument("--image-source-root", default=None)
    parser.add_argument("--image-cache-root", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--canonicalize-intents",
        action="store_true",
        help="Normalize only out-of-vocabulary CMGE intent labels before writing predictions.",
    )
    return parser


def _canonicalize_output(prediction: str) -> tuple[str, Dict[str, Any]]:
    try:
        plan = parse_json_response(prediction)
    except Exception as exc:
        return prediction, {
            "schema_version": "cmge.intent_canonicalization.v1",
            "status": "skipped_parse_error",
            "changed": False,
            "changes": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    normalized, changes = canonicalize_cmge_plan(plan)
    return cmge_canonical_json(normalized), {
        "schema_version": "cmge.intent_canonicalization.v1",
        "status": "applied",
        "changed": bool(changes),
        "changes": changes,
    }


def _completed(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    return {str(row["id"]): row for row in read_jsonl(path)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    records = read_jsonl(Path(args.input))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = _completed(output_path) if args.resume else {}
    pending = [record for record in records if str(record["id"]) not in completed]
    if not pending:
        print(f"CMGE_QWEN3_VL_PREDICT_OK records={len(records)} output={output_path}")
        return 0

    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    model_path = str(args.model_path or config["local_path"])
    max_image_pixels = int(args.max_image_pixels or config.get("max_image_pixels", 1048576))
    processor = AutoProcessor.from_pretrained(
        model_path,
        max_pixels=max_image_pixels,
        local_files_only=True,
        trust_remote_code=bool(config.get("trust_remote_code", False)),
    )
    processor.tokenizer.padding_side = "left"
    dtype = torch.bfloat16 if config.get("dtype") == "bfloat16" else torch.float16
    started = time.perf_counter()
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
    print(f"BACKBONE_LOADED seconds={time.perf_counter() - started:.2f}", flush=True)

    mode = "a" if args.resume and output_path.exists() else "w"
    completed_count = len(completed)
    with output_path.open(mode, encoding="utf-8", newline="\n") as handle:
        for batch_index, batch in enumerate(iter_batches(pending, args.batch_size), start=1):
            conversations: List[List[Dict[str, Any]]] = [
                cmge_planner_messages(record) for record in batch
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
            generated_started = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(
                    **inputs,
                    max_new_tokens=max(args.max_new_tokens, 1),
                    do_sample=False,
                )
            elapsed = time.perf_counter() - generated_started
            trimmed = generated[:, inputs["input_ids"].shape[1] :]
            outputs = processor.batch_decode(
                trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
            token_counts = [
                int((tokens != processor.tokenizer.pad_token_id).sum().item())
                for tokens in trimmed
            ]
            for record, prediction, token_count in zip(batch, outputs, token_counts):
                raw_prediction = prediction.strip()
                canonicalization = None
                written_prediction = raw_prediction
                if args.canonicalize_intents:
                    written_prediction, canonicalization = _canonicalize_output(raw_prediction)
                row = {
                    "id": str(record["id"]),
                    "prediction": written_prediction,
                    "inference": {
                        "batch_index": batch_index,
                        "batch_seconds": elapsed,
                        "model_id": config["model_id"],
                        "revision": config["revision"],
                        "adapter_path": args.adapter_path,
                        "generated_tokens": token_count,
                        "max_image_pixels": max_image_pixels,
                    },
                }
                if canonicalization is not None:
                    row["intent_canonicalization"] = canonicalization
                    if canonicalization["changed"]:
                        row["raw_prediction"] = raw_prediction
                handle.write(
                    canonical_json(row)
                    + "\n"
                )
                handle.flush()
            completed_count += len(batch)
            print(
                f"BATCH_OK index={batch_index} completed={completed_count} "
                f"seconds={elapsed:.2f} generated_tokens={sum(token_counts)} "
                f"peak_gpu_gib={torch.cuda.max_memory_allocated() / (1024 ** 3):.2f}",
                flush=True,
            )
    print(f"CMGE_QWEN3_VL_PREDICT_OK records={len(records)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
