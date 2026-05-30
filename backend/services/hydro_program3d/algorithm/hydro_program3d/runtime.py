from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import torch

from .model import HydroProgram3D
from .schema import ProgramBundle, bundle_from_dict

CLIP_WEIGHT_FILENAMES = (
    "open_clip_pytorch_model.bin",
    "pytorch_model.bin",
    "open_clip_model.safetensors",
)


def _normalize_state_dict_keys(state_dict: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        str(key)[7:] if str(key).startswith("module.") else str(key): value
        for key, value in state_dict.items()
    }


def _normalize_point_encoder_type(value: Any) -> str:
    key = str(value or "mlp").strip().lower()
    if key in {"spvcnn", "spconv"}:
        return "spconv"
    return key or "mlp"


def _normalize_text_encoder_type(value: Any) -> str:
    key = str(value or "simple").strip().lower()
    return key or "simple"


def _has_clip_weights(path: Optional[Path]) -> bool:
    return bool(path and path.is_dir() and any((path / name).exists() for name in CLIP_WEIGHT_FILENAMES))


def _resolve_clip_local_dir(
    config: Mapping[str, Any],
    checkpoint_path: Optional[Union[str, Path]] = None,
) -> Optional[str]:
    raw_text_encoder = config.get("text_encoder", config.get("text_encoder_type", "simple"))
    if _normalize_text_encoder_type(raw_text_encoder) != "clip":
        return None

    checkpoint = Path(checkpoint_path).resolve() if checkpoint_path else None
    configured = config.get("clip_local_dir")
    if configured:
        configured_path = Path(str(configured))
        candidates: List[Path] = []
        if configured_path.is_absolute():
            candidates.append(configured_path)
        elif checkpoint is not None:
            candidates.append((checkpoint.parent / configured_path).resolve())
        candidates.append(configured_path)
        for candidate in candidates:
            if _has_clip_weights(candidate):
                return str(candidate)
        return str(candidates[0])

    if checkpoint is None:
        return None

    root = checkpoint if checkpoint.is_dir() else checkpoint.parent
    candidates = [
        root / "clip",
        root / "clip_weights",
        root / "open_clip",
        root / checkpoint.stem / "clip",
        root / checkpoint.stem,
        root,
    ]
    for candidate in candidates:
        if _has_clip_weights(candidate):
            return str(candidate)
    return None


def parse_path_mappings(values: Optional[Union[str, Iterable[str]]]) -> Optional[List[Tuple[str, str]]]:
    if not values:
        return None
    if isinstance(values, str):
        values = [values]
    mappings: List[Tuple[str, str]] = []
    for item in values:
        if "=" not in item:
            raise ValueError(f"Invalid --path-map value {item!r}; expected SRC=DST")
        src, dst = item.split("=", 1)
        src = src.strip()
        dst = dst.strip()
        if not src or not dst:
            raise ValueError(f"Invalid --path-map value {item!r}; expected SRC=DST")
        mappings.append((src, dst))
    return mappings


def resolve_model_flags(config: Mapping[str, Any]) -> Tuple[bool, str]:
    model_type = str(config.get("model_type", "program"))
    if "use_program_executor" in config:
        use_program_executor = bool(config["use_program_executor"])
    else:
        use_program_executor = model_type != "direct_matching"
    text_source = str(config.get("text_source", "raw"))
    return use_program_executor, text_source


def build_model_kwargs(
    config: Mapping[str, Any],
    checkpoint_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    use_program_executor, text_source = resolve_model_flags(config)
    if "use_ortho_prior" in config:
        use_ortho_prior = bool(config["use_ortho_prior"])
    else:
        use_ortho_prior = not bool(config.get("disable_ortho_prior", False))
    kwargs = {
        "hidden_dim": int(config.get("hidden_dim", 128)),
        "num_classes": int(config.get("num_classes", 15)),
        "geometry_feature_dim": int(config.get("geometry_feature_dim", 4)),
        "point_encoder_type": _normalize_point_encoder_type(
            config.get("point_encoder", config.get("point_encoder_type", "mlp"))
        ),
        "text_encoder_type": _normalize_text_encoder_type(
            config.get("text_encoder", config.get("text_encoder_type", "simple"))
        ),
        "clip_model_name": str(config.get("clip_model_name", "ViT-B-32")),
        "clip_pretrained": str(config.get("clip_pretrained", "openai")),
        "clip_local_dir": _resolve_clip_local_dir(config, checkpoint_path=checkpoint_path),
        "use_ortho_prior": use_ortho_prior,
        "ortho_token_grid": int(config.get("ortho_token_grid", 16)),
        "ortho_y_flip": bool(config.get("ortho_y_flip", True)),
        "point_chunk_size": int(config.get("point_chunk_size", 4096)),
        "use_program_executor": use_program_executor,
        "text_source": text_source,
        "program_residual_weight": float(config.get("program_residual_weight", 0.15)),
        "program_schema_mode": str(config.get("program_schema_mode", "field")),
        "program_version": str(config.get("program_version", "v3_operatorized")),
    }

    if kwargs["point_encoder_type"] == "spconv":
        kwargs["spv_scale_list"] = tuple(config.get("spv_scale_list", (2, 4, 8, 16)))
        kwargs["spv_spatial_shape"] = tuple(config.get("spv_spatial_shape", (23088, 73472, 880)))
        kwargs["spv_min_volume_space"] = tuple(config.get("spv_min_volume_space", (-4654.0, -5286.0, -88.0)))
        kwargs["spv_max_volume_space"] = tuple(config.get("spv_max_volume_space", (1116.0, 13082.0, 129.0)))
    elif kwargs["point_encoder_type"] == "openscene":
        kwargs["voxel_size"] = float(config.get("voxel_size", 0.05))

    return kwargs


def instantiate_model(
    config: Mapping[str, Any],
    device: Optional[torch.device] = None,
    checkpoint_path: Optional[Union[str, Path]] = None,
) -> HydroProgram3D:
    model_kwargs = build_model_kwargs(config, checkpoint_path=checkpoint_path)
    if model_kwargs.get("point_encoder_type") == "spconv" and (device is None or device.type != "cuda"):
        raise ValueError(
            "point_encoder_type='spconv' requires CUDA because spconv implicit GEMM kernels do not run on CPU. "
            "Start the container with '--gpus all' and call /execute with device='cuda'."
        )
    model = HydroProgram3D(**model_kwargs)
    if device is not None:
        model = model.to(device)
    return model


def load_checkpoint_model(
    checkpoint_path: str,
    device: torch.device,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Tuple[HydroProgram3D, Dict[str, Any], Dict[str, Any]]:
    payload = torch.load(checkpoint_path, map_location=device)
    base_config = {}
    if "model_kwargs" in payload:
        base_config.update(payload["model_kwargs"])
    if "args" in payload:
        base_config.update(payload["args"])
    if overrides:
        base_config.update(dict(overrides))
    model = instantiate_model(base_config, device=device, checkpoint_path=checkpoint_path)
    model.load_state_dict(_normalize_state_dict_keys(payload["model"]))
    return model, payload, base_config


def select_counterfactual_program_batch(batch: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], torch.Tensor]:
    programs = list(batch["program"])
    bundles = list(batch.get("program_bundle", []))
    active = []
    selected = []
    for index, (original, counterfactuals) in enumerate(zip(programs, batch.get("counterfactual_programs", []))):
        if counterfactuals:
            selected.append(counterfactuals[0])
            active.append(True)
        else:
            if index < len(bundles):
                try:
                    bundle = bundle_from_dict(bundles[index])
                    selected.append(bundle.selected_program().to_dict())
                except Exception:
                    selected.append(original)
            else:
                selected.append(original)
            active.append(False)
    return selected, torch.tensor(active, dtype=torch.bool)


def select_program_batch(batch: Dict[str, Any]) -> List[Dict[str, Any]]:
    bundles = list(batch.get("program_bundle", []))
    if not bundles:
        return list(batch["program"])
    selected: List[Dict[str, Any]] = []
    for bundle_payload, fallback_program in zip(bundles, batch["program"]):
        try:
            bundle = bundle_from_dict(bundle_payload)
            selected.append(bundle.selected_program().to_dict())
        except Exception:
            selected.append(fallback_program)
    return selected


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
