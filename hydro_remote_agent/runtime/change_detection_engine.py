from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np


@dataclass(frozen=True)
class ChangeDetectionPrediction:
    probability_map: np.ndarray
    original_size: Tuple[int, int]
    device: str


class ChangeDetectionInferenceEngine:
    """Lazy RFANet inference engine using the vendored implementation."""

    def __init__(
        self,
        checkpoint_path: str | Path,
        vendor_root: str | Path,
        device: str = "cuda:0",
        input_size: int = 256,
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path).resolve()
        self.vendor_root = Path(vendor_root).resolve()
        self.device_name = device
        self.input_size = int(input_size)
        self._model: Any = None
        self._torch: Any = None
        self._cv2: Any = None
        self.load_report: Dict[str, Tuple[str, ...]] = {
            "missing_keys": (),
            "unexpected_keys": (),
        }

    @property
    def initialized(self) -> bool:
        return self._model is not None

    def prepare(self) -> None:
        if self.initialized:
            return
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(f"Missing change-detection checkpoint: {self.checkpoint_path}")
        if not self.vendor_root.is_dir():
            raise FileNotFoundError(f"Missing change-detection vendor root: {self.vendor_root}")

        import cv2
        import torch

        vendor_text = str(self.vendor_root)
        if vendor_text not in sys.path:
            sys.path.insert(0, vendor_text)
        from final_model import final_BaseNet

        model = final_BaseNet(3, 1)
        payload = torch.load(self.checkpoint_path, map_location=self.device_name)
        state_dict = payload.get("state_dict", payload) if isinstance(payload, dict) else payload
        if not isinstance(state_dict, dict):
            raise TypeError(f"Unsupported checkpoint payload in {self.checkpoint_path}")
        filtered: Dict[str, Any] = {}
        for key, value in state_dict.items():
            if ".total_ops" in key or ".total_params" in key:
                continue
            normalized_key = key[7:] if key.startswith("module.") else key
            filtered[normalized_key] = value
        incompatible = model.load_state_dict(filtered, strict=False)
        missing_keys = tuple(incompatible.missing_keys)
        unexpected_keys = tuple(incompatible.unexpected_keys)
        self.load_report = {
            "missing_keys": missing_keys,
            "unexpected_keys": unexpected_keys,
        }
        if missing_keys or unexpected_keys:
            raise ValueError(
                "RFANet checkpoint mismatch: "
                f"missing={list(missing_keys)[:10]}, unexpected={list(unexpected_keys)[:10]}"
            )
        self._model = model.to(self.device_name).eval()
        self._torch = torch
        self._cv2 = cv2

    def predict(
        self,
        before_image_path: str | Path,
        after_image_path: str | Path,
    ) -> ChangeDetectionPrediction:
        if not self.initialized:
            raise RuntimeError("Change-detection engine has not been prepared")
        before_path = Path(before_image_path)
        after_path = Path(after_image_path)
        if not before_path.is_file():
            raise FileNotFoundError(f"Missing before image: {before_path}")
        if not after_path.is_file():
            raise FileNotFoundError(f"Missing after image: {after_path}")

        before = self._cv2.imread(str(before_path), self._cv2.IMREAD_COLOR)
        after = self._cv2.imread(str(after_path), self._cv2.IMREAD_COLOR)
        if before is None:
            raise ValueError(f"Failed to decode before image: {before_path}")
        if after is None:
            raise ValueError(f"Failed to decode after image: {after_path}")
        if before.shape[:2] != after.shape[:2]:
            raise ValueError(
                "Before and after images must have identical pixel dimensions: "
                f"{before.shape[:2]} != {after.shape[:2]}"
            )

        original_height, original_width = after.shape[:2]
        paired = np.concatenate((before, after), axis=2).astype(np.float32) / 255.0
        means = np.asarray([0.406, 0.456, 0.485, 0.406, 0.456, 0.485], dtype=np.float32)
        stds = np.asarray([0.225, 0.224, 0.229, 0.225, 0.224, 0.229], dtype=np.float32)
        paired = (paired - means) / stds
        paired = self._cv2.resize(
            paired,
            (self.input_size, self.input_size),
            interpolation=self._cv2.INTER_LINEAR,
        )
        paired = paired[:, :, ::-1].copy().transpose(2, 0, 1)
        tensor = self._torch.from_numpy(paired).unsqueeze(0).float().to(self.device_name)
        with self._torch.no_grad():
            output = self._model(tensor[:, :3], tensor[:, 3:6])[0]
        probability = output[0, 0].detach().cpu().numpy().astype(np.float32)
        probability = self._cv2.resize(
            probability,
            (original_width, original_height),
            interpolation=self._cv2.INTER_LINEAR,
        ).astype(np.float32)
        probability = np.clip(probability, 0.0, 1.0)
        return ChangeDetectionPrediction(
            probability_map=probability,
            original_size=(original_height, original_width),
            device=self.device_name,
        )

    def shutdown(self) -> None:
        self._model = None
        if self._torch is not None and str(self.device_name).startswith("cuda"):
            self._torch.cuda.empty_cache()


class ChangeDetectionEnginePool:
    _engines: Dict[Tuple[str, ...], ChangeDetectionInferenceEngine] = {}
    _lock = threading.Lock()

    @classmethod
    def get(
        cls,
        checkpoint_path: str | Path,
        vendor_root: str | Path,
        device: str = "cuda:0",
        input_size: int = 256,
    ) -> ChangeDetectionInferenceEngine:
        key = (
            str(Path(checkpoint_path).resolve()),
            str(Path(vendor_root).resolve()),
            device,
            str(input_size),
        )
        with cls._lock:
            if key not in cls._engines:
                cls._engines[key] = ChangeDetectionInferenceEngine(
                    checkpoint_path=checkpoint_path,
                    vendor_root=vendor_root,
                    device=device,
                    input_size=input_size,
                )
            return cls._engines[key]
