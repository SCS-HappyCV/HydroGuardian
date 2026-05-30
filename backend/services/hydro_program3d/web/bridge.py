from __future__ import annotations

import importlib
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

import torch

from .config import ServiceSettings, load_settings

CLIP_WEIGHT_FILENAMES = (
    "open_clip_pytorch_model.bin",
    "pytorch_model.bin",
    "open_clip_model.safetensors",
)


class HydroProgramBridge:
    def __init__(self, settings: Optional[ServiceSettings] = None) -> None:
        self.settings = settings or load_settings()
        self._model = None
        self._model_payload = None
        self._model_base_config: Optional[Dict[str, Any]] = None
        self._compiler = None
        self._compiler_error: Optional[str] = None
        self._model_error: Optional[str] = None

    def ensure_algorithm_path(self) -> None:
        algorithm_dir = self.settings.algorithm_dir
        if not algorithm_dir.exists():
            raise FileNotFoundError(f"Algorithm dir not found: {algorithm_dir}")
        path_str = str(algorithm_dir)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

    def load_compiler(self):
        if self._compiler is not None:
            return self._compiler
        try:
            self.ensure_algorithm_path()
            module = importlib.import_module("hydro_program3d.evidence_compiler")
            self._compiler = module.EvidenceCompiler()
            self._compiler_error = None
            return self._compiler
        except Exception as exc:
            self._compiler_error = str(exc)
            raise

    def _checkpoint_path(self, checkpoint_name: Optional[str]) -> Optional[Path]:
        if not checkpoint_name:
            return None
        candidate = self.settings.checkpoint_dir / checkpoint_name
        if candidate.exists():
            return candidate
        if candidate.suffix.lower() in {".pt", ".pth", ".bin"}:
            return candidate
        for suffix in (".pt", ".pth", ".bin"):
            suffixed = candidate.with_suffix(suffix)
            if suffixed.exists():
                return suffixed
        return candidate

    def _has_clip_weights(self, path: Optional[Path]) -> bool:
        return bool(path and path.is_dir() and any((path / name).exists() for name in CLIP_WEIGHT_FILENAMES))

    def _prepare_model_overrides(
        self,
        overrides: Optional[Dict[str, Any]],
        checkpoint_path: Optional[Path],
    ) -> Dict[str, Any]:
        model_kwargs = dict(overrides or {})
        point_encoder_type = str(
            model_kwargs.get("point_encoder_type", model_kwargs.get("point_encoder", ""))
        ).strip().lower()
        if point_encoder_type in {"spvcnn", "spconv"}:
            model_kwargs["point_encoder_type"] = "spconv"

        text_encoder_type = str(
            model_kwargs.get("text_encoder_type", model_kwargs.get("text_encoder", ""))
        ).strip().lower()
        clip_local_dir = model_kwargs.get("clip_local_dir")
        if clip_local_dir:
            clip_dir = Path(str(clip_local_dir))
            if not clip_dir.is_absolute():
                checkpoint_root = checkpoint_path.parent if checkpoint_path and checkpoint_path.exists() else self.settings.checkpoint_dir
                candidate = checkpoint_root / clip_dir
                if self._has_clip_weights(candidate):
                    model_kwargs["clip_local_dir"] = str(candidate)
                else:
                    model_kwargs["clip_local_dir"] = str((self.settings.service_root / clip_dir).resolve())
        elif text_encoder_type == "clip":
            checkpoint_root = checkpoint_path.parent if checkpoint_path and checkpoint_path.exists() else self.settings.checkpoint_dir
            candidates = [
                checkpoint_root / "clip",
                checkpoint_root / "clip_weights",
                checkpoint_root / "open_clip",
                checkpoint_root,
            ]
            if checkpoint_path is not None:
                candidates.extend(
                    [
                        checkpoint_root / checkpoint_path.stem / "clip",
                        checkpoint_root / checkpoint_path.stem,
                    ]
                )
            for candidate in candidates:
                if self._has_clip_weights(candidate):
                    model_kwargs["clip_local_dir"] = str(candidate)
                    break
        return model_kwargs

    def _resolve_device(self, device: Optional[str]) -> torch.device:
        if device:
            torch_device = torch.device(device)
        elif torch.cuda.is_available():
            torch_device = torch.device("cuda")
        else:
            torch_device = torch.device("cpu")
        if torch_device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("device='cuda' was requested, but CUDA is not available inside the container.")
        return torch_device

    def load_model(self, checkpoint_name: Optional[str] = None, device: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None):
        if self._model is not None and checkpoint_name is None and not overrides and device is None:
            return self._model, self._model_payload, self._model_base_config or {}
        try:
            self.ensure_algorithm_path()
            runtime = importlib.import_module("hydro_program3d.runtime")
            checkpoint_path = self._checkpoint_path(checkpoint_name)
            model_kwargs = self._prepare_model_overrides(overrides, checkpoint_path)
            torch_device = self._resolve_device(device)
            if checkpoint_path is None:
                model = runtime.instantiate_model(model_kwargs, device=torch_device)
                model.eval()
                self._model = model
                self._model_payload = None
                self._model_base_config = dict(model_kwargs)
                self._model_error = None
                return model, None, dict(model_kwargs)
            model, payload, base_config = runtime.load_checkpoint_model(str(checkpoint_path), device=torch_device, overrides=model_kwargs)
            model.eval()
            self._model = model
            self._model_payload = payload
            self._model_base_config = dict(base_config)
            self._model_error = None
            return model, payload, base_config
        except Exception as exc:
            self._model_error = str(exc)
            raise

    def execute(self, sample: Dict[str, Any], program: Optional[Dict[str, Any]] = None, program_bundle: Optional[Dict[str, Any]] = None, checkpoint_name: Optional[str] = None, device: Optional[str] = None, model_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        model, payload, base_config = self.load_model(checkpoint_name=checkpoint_name, device=device, overrides=model_overrides)

        sample_tensors = {}
        for key in ("images", "points_xyz", "points_rgb", "point_geometry_features", "valid_point_mask"):
            value = sample.get(key)
            if value is not None:
                sample_tensors[key] = torch.as_tensor(value)
        images = sample_tensors.get("images")
        points_xyz = sample_tensors.get("points_xyz")
        points_rgb = sample_tensors.get("points_rgb")
        point_geometry_features = sample_tensors.get("point_geometry_features")
        valid_point_mask = sample_tensors.get("valid_point_mask")
        if images is None or points_xyz is None or points_rgb is None or point_geometry_features is None:
            raise ValueError("sample must include images, points_xyz, points_rgb, and point_geometry_features.")
        model_device = next(model.parameters()).device
        if images.ndim == 3:
            images = images.unsqueeze(0)
        if points_xyz.ndim == 2:
            points_xyz = points_xyz.unsqueeze(0)
        if points_rgb.ndim == 2:
            points_rgb = points_rgb.unsqueeze(0)
        if point_geometry_features.ndim == 2:
            point_geometry_features = point_geometry_features.unsqueeze(0)
        if valid_point_mask is not None and valid_point_mask.ndim == 1:
            valid_point_mask = valid_point_mask.unsqueeze(0)

        images = images.to(model_device).float()
        points_xyz = points_xyz.to(model_device).float()
        points_rgb = points_rgb.to(model_device).float()
        point_geometry_features = point_geometry_features.to(model_device).float()
        if valid_point_mask is not None:
            valid_point_mask = valid_point_mask.to(model_device).bool()

        program_args = {}
        if program_bundle is not None:
            program_args["program_bundles"] = [program_bundle]
        elif program is not None:
            program_args["programs"] = [program]
        elif "texts" in sample:
            program_args["texts"] = [sample["texts"]] if isinstance(sample["texts"], str) else list(sample["texts"])
        elif "text" in sample:
            program_args["texts"] = [sample["text"]]
        else:
            raise ValueError("execute requires program, program_bundle, text, or texts in sample.")

        with torch.no_grad():
            outputs = model(
                images=images,
                points_xyz=points_xyz,
                points_rgb=points_rgb,
                point_geometry_features=point_geometry_features,
                valid_point_mask=valid_point_mask,
                **program_args,
            )

        return {
            "ok": True,
            "message": "executed",
            "service_root": str(self.settings.service_root),
            "algorithm_dir": str(self.settings.algorithm_dir),
            "checkpoint_name": checkpoint_name,
            "checkpoint_path": str(self._checkpoint_path(checkpoint_name)) if checkpoint_name else None,
            "model_config": self._jsonable(base_config),
            "device": str(model_device),
            "sample": self._jsonable(sample),
            "program": self._jsonable(program),
            "program_bundle": self._jsonable(program_bundle),
            "outputs": {key: self._jsonable(value) for key, value in outputs.items()},
        }

    def compile_evidence(self, sample: Dict[str, Any], outputs: Dict[str, Any], batch_index: int = 0) -> Dict[str, Any]:
        compiler = self.load_compiler()
        pack = compiler.compile(sample, outputs, batch_index=batch_index)
        if hasattr(pack, "to_dict"):
            return pack.to_dict()
        if hasattr(pack, "__dict__"):
            return asdict(pack)
        return {"value": str(pack)}

    def compile_batch(self, batch: Dict[str, Any], outputs: Dict[str, Any]) -> Dict[str, Any]:
        compiler = self.load_compiler()
        packs = compiler.compile_batch(batch, outputs)
        result = []
        for pack in packs:
            if hasattr(pack, "to_dict"):
                result.append(pack.to_dict())
            elif hasattr(pack, "__dict__"):
                result.append(asdict(pack))
            else:
                result.append({"value": str(pack)})
        return {"evidence_packs": result}

    @property
    def compiler_available(self) -> bool:
        try:
            self.load_compiler()
            return True
        except Exception:
            return False

    @property
    def compiler_error(self) -> Optional[str]:
        return self._compiler_error

    @property
    def model_error(self) -> Optional[str]:
        return self._model_error

    def _jsonable(self, value: Any) -> Any:
        if isinstance(value, torch.Tensor):
            tensor = value.detach().cpu()
            if tensor.ndim == 0:
                return tensor.item()
            return tensor.tolist()
        if isinstance(value, dict):
            return {str(key): self._jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._jsonable(item) for item in value]
        if hasattr(value, "to_dict"):
            return self._jsonable(value.to_dict())
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)
