from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


def parse_json_object(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("model response must be a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke-test a local Qwen3-VL backbone.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    model_path = Path(config["local_path"])
    image_path = Path(args.image)
    if not model_path.exists() or not image_path.is_file():
        raise FileNotFoundError("model or smoke-test image does not exist")

    import torch
    import transformers
    from PIL import Image
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available")
    dtype = torch.bfloat16 if config.get("dtype") == "bfloat16" else torch.float16
    processor = AutoProcessor.from_pretrained(
        str(model_path),
        max_pixels=int(config.get("max_image_pixels", 1024 * 1024)),
        trust_remote_code=bool(config.get("trust_remote_code", False)),
        local_files_only=True,
    )
    started = time.perf_counter()
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        str(model_path),
        dtype=dtype,
        device_map={"": 0},
        attn_implementation="sdpa",
        trust_remote_code=bool(config.get("trust_remote_code", False)),
        local_files_only=True,
    ).eval()
    load_seconds = time.perf_counter() - started

    prompt = (
        "Inspect this hydrological remote-sensing image. Return only one JSON object with "
        "keys scene_summary, visible_land_cover, and confidence. Do not use Markdown."
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": str(image_path)},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    ).to("cuda")
    torch.cuda.reset_peak_memory_stats()
    infer_started = time.perf_counter()
    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            max_new_tokens=max(int(args.max_new_tokens), 1),
            do_sample=False,
        )
    inference_seconds = time.perf_counter() - infer_started
    trimmed = generated[:, inputs["input_ids"].shape[1] :]
    text = processor.batch_decode(
        trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False,
    )[0]
    parsed = parse_json_object(text)
    with Image.open(image_path) as image:
        image_size = list(image.size)
    manifest_path = model_path / "vaguehydro_model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = {
        "schema_version": "vague_hydro.backbone_smoke.v1",
        "status": "passed",
        "model_id": config["model_id"],
        "revision": manifest["resolved_revision"],
        "image_path": str(image_path),
        "image_size": image_size,
        "load_seconds": load_seconds,
        "inference_seconds": inference_seconds,
        "peak_gpu_memory_gb": torch.cuda.max_memory_allocated() / (1024 ** 3),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "raw_output": text,
        "parsed_output": parsed,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"QWEN3_VL_SMOKE_OK load={load_seconds:.2f}s infer={inference_seconds:.2f}s "
        f"peak_gpu_gb={report['peak_gpu_memory_gb']:.2f} output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
