from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import (
    assistant_target,
    canonical_json,
    planner_training_messages,
)
from hydro_remote_agent.cmge_planner import (
    cmge_assistant_target,
    cmge_training_messages,
)


SFT_TARGET_FORMATS = ("agent_request", "cmge")


def training_messages(
    record: Mapping[str, Any],
    target_format: str,
) -> List[Dict[str, Any]]:
    if target_format == "agent_request":
        return planner_training_messages(record)
    if target_format == "cmge":
        return cmge_training_messages(record)
    raise ValueError(f"unsupported SFT target format: {target_format!r}")


def training_target(record: Mapping[str, Any], target_format: str) -> Dict[str, Any]:
    if target_format == "agent_request":
        return assistant_target(record)
    if target_format == "cmge":
        return cmge_assistant_target(record)
    raise ValueError(f"unsupported SFT target format: {target_format!r}")


class JsonlOffsetDataset:
    def __init__(self, path: str | Path, max_samples: Optional[int] = None) -> None:
        self.path = Path(path)
        self.offsets: List[int] = []
        with self.path.open("rb") as handle:
            while max_samples is None or len(self.offsets) < max_samples:
                offset = handle.tell()
                line = handle.readline()
                if not line:
                    break
                if line.strip():
                    self.offsets.append(offset)

    def __len__(self) -> int:
        return len(self.offsets)

    def __getitem__(self, index: int) -> Dict[str, Any]:
        with self.path.open("rb") as handle:
            handle.seek(self.offsets[index])
            payload = json.loads(handle.readline())
        if not isinstance(payload, dict):
            raise ValueError(f"{self.path} record {index} must be an object")
        return payload


def find_last_subsequence(sequence: Sequence[int], target: Sequence[int]) -> int:
    if not target or len(target) > len(sequence):
        return -1
    for start in range(len(sequence) - len(target), -1, -1):
        if list(sequence[start : start + len(target)]) == list(target):
            return start
    return -1


@dataclass
class Qwen3VLSFTCollator:
    processor: Any
    max_length: int = 16384
    image_source_root: Optional[str] = None
    image_cache_root: Optional[str] = None
    target_format: str = "agent_request"

    def __call__(self, records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        import torch

        conversations = [
            training_messages(record, self.target_format) for record in records
        ]
        if self.image_source_root and self.image_cache_root:
            source = self.image_source_root.rstrip("/\\")
            target = self.image_cache_root.rstrip("/\\")
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
        batch = self.processor.apply_chat_template(
            conversations,
            tokenize=True,
            add_generation_prompt=False,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_dict=True,
            return_tensors="pt",
        )
        labels = torch.full_like(batch["input_ids"], -100)
        for index, record in enumerate(records):
            target_text = canonical_json(training_target(record, self.target_format))
            target_ids = self.processor.tokenizer.encode(
                target_text,
                add_special_tokens=False,
            )
            input_ids = batch["input_ids"][index].tolist()
            start = find_last_subsequence(input_ids, target_ids)
            if start < 0:
                raise ValueError(
                    f"assistant target for {record.get('id')!r} was truncated or not tokenized verbatim"
                )
            valid_length = int(batch["attention_mask"][index].sum().item())
            labels[index, start:valid_length] = batch["input_ids"][index, start:valid_length]
        batch["labels"] = labels
        return dict(batch)


def load_training_config(path: str | Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError("training config must contain an object")
    return config
