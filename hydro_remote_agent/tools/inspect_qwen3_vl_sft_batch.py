from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.training.qwen3_vl_sft import JsonlOffsetDataset, Qwen3VLSFTCollator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect one processed Qwen3-VL SFT batch.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--index", type=int, default=0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    backbone = json.loads(Path(config["backbone_config"]).read_text(encoding="utf-8"))
    from transformers import AutoProcessor

    processor = AutoProcessor.from_pretrained(
        backbone["local_path"],
        max_pixels=int(config["data"]["max_image_pixels"]),
        local_files_only=True,
    )
    processor.tokenizer.padding_side = "right"
    dataset = JsonlOffsetDataset(config["data"]["train_file"])
    record = dataset[args.index]
    batch = Qwen3VLSFTCollator(
        processor=processor,
        max_length=int(config["data"]["max_length"]),
        image_source_root=config["data"].get("image_source_root"),
        image_cache_root=config["data"].get("image_cache_root"),
        target_format=str(config["data"].get("target_format", "agent_request")),
    )([record])
    report = {
        "id": record["id"],
        "input_tokens": int(batch["attention_mask"].sum().item()),
        "supervised_tokens": int((batch["labels"] != -100).sum().item()),
        "image_grid_thw": batch.get("image_grid_thw").tolist()
        if batch.get("image_grid_thw") is not None
        else None,
        "pixel_values_shape": list(batch["pixel_values"].shape)
        if batch.get("pixel_values") is not None
        else None,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
