from __future__ import annotations

import random
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class PointceptPrediction:
    point_labels: np.ndarray
    class_probabilities: np.ndarray
    num_points: int
    device: str
    sample_id: str
    checkpoint_epoch: int


class PointceptPtv3InferenceEngine:
    """Pointcept PTv3 inference with exact original-point replay."""

    def __init__(
        self,
        checkpoint_path: str | Path,
        config_path: str | Path,
        vendor_root: str | Path,
        device: str = "cuda:0",
        split: str = "test",
        split_root: str | Path | None = None,
        python_paths: Sequence[str | Path] = (),
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path).resolve()
        self.config_path = Path(config_path).resolve()
        self.vendor_root = Path(vendor_root).resolve()
        self.device_name = device
        self.split = split
        self.split_root = Path(split_root).resolve() if split_root is not None else None
        self.python_paths = tuple(Path(path).resolve() for path in python_paths)
        self._model: Any = None
        self._dataset: Any = None
        self._collate_fn: Any = None
        self._torch: Any = None
        self._functional: Any = None
        self._sample_to_index: Dict[str, int] = {}
        self._checkpoint_epoch = -1
        self._base_seed = 0
        self._lock = threading.Lock()

    @property
    def initialized(self) -> bool:
        return self._model is not None and self._dataset is not None

    @staticmethod
    def sample_id_from_path(path: str | Path) -> str:
        point_path = Path(path)
        if not point_path.is_file():
            raise FileNotFoundError(f"Missing point cloud: {point_path}")
        folder = point_path.parent.parent.name
        if not folder or point_path.parent.name != "velodyne":
            raise ValueError(
                "Pointcept WCS10M inputs must use <folder>/velodyne/<patch> layout: "
                f"{point_path}"
            )
        return f"{folder}_{point_path.stem}"

    def prepare(self) -> None:
        if self.initialized:
            return
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(f"Missing Pointcept checkpoint: {self.checkpoint_path}")
        if not self.config_path.is_file():
            raise FileNotFoundError(f"Missing Pointcept config: {self.config_path}")
        if not (self.vendor_root / "pointcept" / "models").is_dir():
            raise FileNotFoundError(f"Incomplete Pointcept source: {self.vendor_root}")

        for import_root in (self.vendor_root, *self.python_paths):
            import_text = str(import_root)
            if import_text not in sys.path:
                sys.path.insert(0, import_text)

        import torch
        import torch.nn.functional as functional
        from pointcept.datasets import build_dataset, collate_fn
        from pointcept.models import build_model
        from pointcept.utils.config import Config

        if self.device_name.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError(f"CUDA device {self.device_name!r} requested but CUDA is unavailable")

        config = Config.fromfile(str(self.config_path))
        config.data.test.split = self.split
        if self.split_root is not None:
            config.data.test.split_root = str(self.split_root)
        dataset = build_dataset(config.data.test)
        model = build_model(config.model).to(self.device_name)
        checkpoint = torch.load(str(self.checkpoint_path), map_location="cpu", weights_only=False)
        raw_state = checkpoint.get("state_dict")
        if not isinstance(raw_state, Mapping):
            raise ValueError(f"Checkpoint {self.checkpoint_path} has no state_dict")
        state = OrderedDict(
            (key[7:] if str(key).startswith("module.") else str(key), value)
            for key, value in raw_state.items()
        )
        incompatible = model.load_state_dict(state, strict=False)
        if incompatible.missing_keys or incompatible.unexpected_keys:
            raise RuntimeError(
                "Pointcept checkpoint mismatch: "
                f"missing={list(incompatible.missing_keys)[:10]}, "
                f"unexpected={list(incompatible.unexpected_keys)[:10]}"
            )
        sample_to_index = {
            str(record["sample_id"]): index for index, record in enumerate(dataset.data_list)
        }
        if len(sample_to_index) != len(dataset.data_list):
            raise ValueError("Pointcept split contains duplicate sample IDs")

        self._torch = torch
        self._functional = functional
        self._collate_fn = collate_fn
        self._dataset = dataset
        self._sample_to_index = sample_to_index
        self._checkpoint_epoch = int(checkpoint.get("epoch", -1))
        self._base_seed = int(getattr(config, "seed", 0))
        self._model = model.eval()

    def predict(self, point_cloud_path: str | Path) -> PointceptPrediction:
        self.prepare()
        sample_id = self.sample_id_from_path(point_cloud_path)
        try:
            sample_index = self._sample_to_index[sample_id]
        except KeyError as exc:
            raise KeyError(
                f"Sample {sample_id!r} is not in Pointcept split {self.split!r}"
            ) from exc

        torch = self._torch
        with self._lock, torch.inference_mode():
            sample_seed = self._base_seed + sample_index
            random.seed(sample_seed)
            np.random.seed(sample_seed)
            torch.manual_seed(sample_seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(sample_seed)

            data = self._dataset[sample_index]
            fragments = data["fragment_list"]
            target = np.asarray(data["segment"], dtype=np.int64)
            accumulated = torch.zeros((len(target), 15), device=self.device_name)
            for fragment in fragments:
                batch = self._collate_fn([fragment])
                for key, value in batch.items():
                    if isinstance(value, torch.Tensor):
                        batch[key] = value.to(self.device_name, non_blocking=True)
                indices = batch["index"]
                fragment_probability = self._functional.softmax(
                    self._model(batch)["seg_logits"], dim=-1
                )
                start = 0
                for end in batch["offset"]:
                    accumulated[indices[start:end]] += fragment_probability[start:end]
                    start = end

            probability_tensor = accumulated
            if "origin_segment" in data:
                if "inverse" not in data:
                    raise KeyError(f"{sample_id}: origin_segment requires inverse")
                inverse = torch.as_tensor(
                    np.asarray(data["inverse"], dtype=np.int64),
                    device=self.device_name,
                    dtype=torch.long,
                )
                probability_tensor = probability_tensor[inverse]
            probability_tensor /= probability_tensor.sum(dim=1, keepdim=True).clamp_min(1e-12)
            probabilities = probability_tensor.cpu().numpy().astype(np.float32)

        source_count = int(np.loadtxt(point_cloud_path, usecols=(0,), ndmin=1).shape[0])
        if len(probabilities) != source_count:
            raise ValueError(
                f"{sample_id}: original-point replay produced {len(probabilities)} labels "
                f"for {source_count} source points"
            )
        labels = probabilities.argmax(axis=1).astype(np.int32) + 1
        return PointceptPrediction(
            point_labels=labels,
            class_probabilities=probabilities,
            num_points=source_count,
            device=self.device_name,
            sample_id=sample_id,
            checkpoint_epoch=self._checkpoint_epoch,
        )

    def shutdown(self) -> None:
        self._model = None
        self._dataset = None
        self._sample_to_index = {}
        if self._torch is not None and self.device_name.startswith("cuda"):
            self._torch.cuda.empty_cache()
        self._torch = None
        self._functional = None
        self._collate_fn = None


class PointceptEnginePool:
    _engines: Dict[Tuple[str, ...], PointceptPtv3InferenceEngine] = {}
    _lock = threading.Lock()

    @classmethod
    def get(
        cls,
        checkpoint_path: str | Path,
        config_path: str | Path,
        vendor_root: str | Path,
        device: str,
        split: str,
        split_root: str | Path | None = None,
        python_paths: Sequence[str | Path] = (),
    ) -> PointceptPtv3InferenceEngine:
        key = tuple(
            str(Path(value).resolve()) for value in (checkpoint_path, config_path, vendor_root)
        ) + (
            device,
            split,
            str(Path(split_root).resolve()) if split_root is not None else "",
        ) + tuple(str(Path(path).resolve()) for path in python_paths)
        with cls._lock:
            engine = cls._engines.get(key)
            if engine is None:
                engine = PointceptPtv3InferenceEngine(
                    checkpoint_path=checkpoint_path,
                    config_path=config_path,
                    vendor_root=vendor_root,
                    device=device,
                    split=split,
                    split_root=split_root,
                    python_paths=python_paths,
                )
                cls._engines[key] = engine
            return engine
