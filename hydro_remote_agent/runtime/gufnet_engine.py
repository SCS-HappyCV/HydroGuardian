from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import numpy as np
import yaml


@dataclass(frozen=True)
class GufnetPrediction:
    point_labels: np.ndarray
    class_probabilities: np.ndarray
    num_points: int
    device: str


def _deep_update(target: Dict[str, Any], source: Mapping[str, Any]) -> Dict[str, Any]:
    for key, value in source.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
    return target


def _to_plain_dict(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _to_plain_dict(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain_dict(child) for child in value]
    return value


class GufnetInferenceEngine:
    """Shared GUFNet 3D inference core loaded once per process and device."""

    def __init__(
        self,
        checkpoint_path: str | Path,
        config_path: str | Path,
        vendor_root: str | Path,
        device: str = "cuda:0",
        max_chunk_points: int = 100_000,
        min_chunk_points: int = 12_500,
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path).resolve()
        self.config_path = Path(config_path).resolve()
        self.vendor_root = Path(vendor_root).resolve()
        self.device_name = device
        self.max_chunk_points = max(int(max_chunk_points), 1)
        self.min_chunk_points = max(min(int(min_chunk_points), self.max_chunk_points), 1)
        self._model: Any = None
        self._torch: Any = None
        self._lock = threading.Lock()

    @property
    def initialized(self) -> bool:
        return self._model is not None

    def prepare(self) -> None:
        if self.initialized:
            return
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(f"Missing GUFNet checkpoint: {self.checkpoint_path}")
        if not self.config_path.is_file():
            raise FileNotFoundError(f"Missing GUFNet config: {self.config_path}")
        if not (self.vendor_root / "network" / "SPVCNN_LGC.py").is_file():
            raise FileNotFoundError(f"Incomplete GUFNet vendor source: {self.vendor_root}")

        import torch
        from easydict import EasyDict

        if self.device_name.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError(f"CUDA device {self.device_name!r} requested but CUDA is unavailable")

        vendor_text = str(self.vendor_root)
        if vendor_text not in sys.path:
            sys.path.insert(0, vendor_text)
        from network.SPVCNN_LGC import get_model as Gufnet3DModel

        with self.config_path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
        if not isinstance(config, dict):
            raise ValueError(f"GUFNet config {self.config_path} must contain an object")

        checkpoint = torch.load(self.checkpoint_path, map_location="cpu")
        checkpoint_config = checkpoint.get("hyper_parameters", {}).get("config", {})
        if isinstance(checkpoint_config, Mapping):
            _deep_update(config, _to_plain_dict(checkpoint_config))
        config.update(
            {
                "test": True,
                "baseline_only": False,
                "submit_to_server": False,
                "save_test_predictions": False,
                "checkpoint": str(self.checkpoint_path),
                "gpu": [0],
                "monitor": "val/mIoU",
            }
        )
        config["dataset_params"]["label_mapping"] = str(
            self.vendor_root / "config" / "label_mapping" / "wcs2d3d.yaml"
        )
        label_weights = config["dataset_params"].get("seg_labelweights")
        if label_weights is not None:
            normalized_weights = list(label_weights)
            if normalized_weights and float(normalized_weights[0]) == 0.0:
                normalized_weights[0] = 1.0
            config["dataset_params"]["seg_labelweights"] = normalized_weights

        model = Gufnet3DModel(EasyDict(config))
        full_state = checkpoint.get("state_dict")
        if not isinstance(full_state, Mapping):
            raise ValueError(f"Checkpoint {self.checkpoint_path} has no state_dict")
        prefix = "model_3d."
        state = {
            key[len(prefix) :]: value
            for key, value in full_state.items()
            if str(key).startswith(prefix)
        }
        if not state:
            raise ValueError("Checkpoint has no model_3d.* weights")
        missing, unexpected = model.load_state_dict(state, strict=False)
        if missing or unexpected:
            raise RuntimeError(
                f"GUFNet 3D checkpoint mismatch: missing={list(missing)[:10]}, "
                f"unexpected={list(unexpected)[:10]}"
            )
        class InferenceCriterion(torch.nn.Module):
            def forward(self, data_dict: Dict[str, Any]) -> Dict[str, Any]:
                return data_dict

        model.criterion = InferenceCriterion()
        self._torch = torch
        self._model = model.to(self.device_name).eval()

    @staticmethod
    def load_point_features(path: str | Path) -> np.ndarray:
        point_path = Path(path)
        if not point_path.is_file():
            raise FileNotFoundError(f"Missing point cloud: {point_path}")
        suffix = point_path.suffix.lower()
        if suffix in {".las", ".laz"}:
            try:
                import laspy
            except ImportError as exc:
                raise RuntimeError("Loading LAS/LAZ point clouds requires laspy") from exc
            cloud = laspy.read(point_path)
            xyz = np.column_stack((cloud.x, cloud.y, cloud.z)).astype(np.float32)
            dimensions = {str(name).lower() for name in cloud.point_format.dimension_names}
            if {"red", "green", "blue"}.issubset(dimensions):
                rgb = np.column_stack((cloud.red, cloud.green, cloud.blue)).astype(np.float32)
                if rgb.size and float(rgb.max()) > 255.0:
                    rgb /= 256.0
                rgb = np.clip(rgb, 0.0, 255.0)
            else:
                rgb = np.zeros((len(xyz), 3), dtype=np.float32)
            points = np.concatenate((xyz, rgb), axis=1)
        elif suffix in {".txt", ".xyz", ".pts", ".csv"}:
            delimiter = "," if suffix == ".csv" else None
            points = np.loadtxt(point_path, delimiter=delimiter, ndmin=2)
        elif suffix == ".npy":
            points = np.load(point_path, allow_pickle=False)
        elif suffix == ".npz":
            with np.load(point_path, allow_pickle=False) as payload:
                key = next((name for name in ("points", "data", "xyzrgb_label") if name in payload), None)
                if key is None:
                    raise ValueError(f"Point NPZ {point_path} has no supported point array")
                points = payload[key]
        elif suffix in {".pt", ".pth"}:
            import torch

            payload = torch.load(point_path, map_location="cpu", weights_only=False)
            if hasattr(payload, "detach"):
                points = payload.detach().cpu().numpy()
            elif isinstance(payload, Mapping):
                value = next(
                    (
                        payload[name]
                        for name in ("points", "data", "xyzrgb_label")
                        if name in payload
                    ),
                    None,
                )
                if value is None:
                    raise ValueError(f"Point PTH {point_path} has no supported point array")
                points = value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)
            else:
                points = np.asarray(payload)
        else:
            raise ValueError(f"Unsupported point-cloud format {suffix!r}: {point_path}")

        points = np.asarray(points, dtype=np.float32)
        if points.ndim != 2 or points.shape[1] < 6:
            raise ValueError(f"Expected XYZRGB point array [N, >=6], got {points.shape}")
        if len(points) == 0:
            raise ValueError(f"Point cloud {point_path} is empty")
        if not np.isfinite(points[:, :6]).all():
            raise ValueError(f"Point cloud {point_path} contains non-finite XYZRGB values")
        xyz = points[:, :3]
        centered_xyz = xyz - xyz.mean(axis=0, keepdims=True)
        return np.concatenate([centered_xyz, points[:, 3:6]], axis=1).astype(np.float32)

    def predict(self, point_cloud_path: str | Path) -> GufnetPrediction:
        self.prepare()
        features = self.load_point_features(point_cloud_path)
        torch = self._torch
        point_labels = np.empty(len(features), dtype=np.int32)
        class_probabilities = np.empty((len(features), 15), dtype=np.float32)
        with self._lock, torch.inference_mode():
            offset = 0
            chunk_points = min(self.max_chunk_points, len(features))
            while offset < len(features):
                stop = min(offset + chunk_points, len(features))
                try:
                    chunk_labels, chunk_probabilities = self._predict_chunk(features[offset:stop])
                except torch.OutOfMemoryError:
                    if not self.device_name.startswith("cuda") or chunk_points <= self.min_chunk_points:
                        raise
                    torch.cuda.empty_cache()
                    chunk_points = max(chunk_points // 2, self.min_chunk_points)
                    continue
                point_labels[offset:stop] = chunk_labels
                class_probabilities[offset:stop] = chunk_probabilities
                offset = stop
        return GufnetPrediction(
            point_labels=point_labels,
            class_probabilities=class_probabilities,
            num_points=len(features),
            device=self.device_name,
        )

    def _predict_chunk(self, features: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        torch = self._torch
        chunk_features = np.asarray(features, dtype=np.float32).copy()
        chunk_features[:, :3] -= chunk_features[:, :3].mean(axis=0, keepdims=True)
        points = torch.from_numpy(chunk_features).to(self.device_name)
        data_dict = {
            "points": points,
            "batch_idx": torch.zeros(len(features), dtype=torch.long, device=self.device_name),
            "batch_size": 1,
            "labels": torch.ones(len(features), dtype=torch.long, device=self.device_name),
        }
        outputs = self._model(data_dict)
        logits = outputs["logits"]
        if logits.ndim != 2 or logits.shape[1] != 16:
            raise RuntimeError(f"Expected GUFNet logits [N, 16], got {tuple(logits.shape)}")
        probabilities = torch.softmax(logits[:, 1:16], dim=1)
        labels = probabilities.argmax(dim=1) + 1
        return (
            labels.cpu().numpy().astype(np.int32),
            probabilities.cpu().numpy().astype(np.float32),
        )

    def shutdown(self) -> None:
        if self._model is None:
            return
        self._model = None
        if self._torch is not None and self.device_name.startswith("cuda"):
            self._torch.cuda.empty_cache()
        self._torch = None


class GufnetEnginePool:
    _engines: Dict[Tuple[str, str, str, str, int, int], GufnetInferenceEngine] = {}
    _lock = threading.Lock()

    @classmethod
    def get(
        cls,
        checkpoint_path: str | Path,
        config_path: str | Path,
        vendor_root: str | Path,
        device: str,
        max_chunk_points: int = 100_000,
        min_chunk_points: int = 12_500,
    ) -> GufnetInferenceEngine:
        key = tuple(
            str(Path(value).resolve())
            for value in (checkpoint_path, config_path, vendor_root)
        ) + (device, int(max_chunk_points), int(min_chunk_points))
        with cls._lock:
            engine = cls._engines.get(key)
            if engine is None:
                engine = GufnetInferenceEngine(
                    checkpoint_path=checkpoint_path,
                    config_path=config_path,
                    vendor_root=vendor_root,
                    device=device,
                    max_chunk_points=max_chunk_points,
                    min_chunk_points=min_chunk_points,
                )
                cls._engines[key] = engine
            return engine
