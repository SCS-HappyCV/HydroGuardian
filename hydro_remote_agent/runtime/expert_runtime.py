from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml

from hydro_remote_agent.schemas.tool_spec import ToolArgumentError, ToolRegistry

from .adapter import ExpertAdapter
from .contracts import ExpertConfigurationError, ExpertHealth, ExpertResult


INVOCATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class ExpertRuntime:
    """Registry-linked router for expert lifecycle and prediction calls."""

    def __init__(self, registry: ToolRegistry, adapters: Mapping[str, ExpertAdapter]) -> None:
        self.registry = registry
        self._adapters = dict(adapters)
        unknown = sorted(set(self._adapters) - set(registry.names()))
        missing = sorted(set(registry.names()) - set(self._adapters))
        if unknown:
            raise ExpertConfigurationError(f"Adapters reference unknown tools: {unknown}")
        if missing:
            raise ExpertConfigurationError(f"Missing adapters for registered tools: {missing}")
        for tool_name, adapter in self._adapters.items():
            if adapter.tool_spec.name != tool_name:
                raise ExpertConfigurationError(
                    f"Adapter key {tool_name!r} does not match ToolSpec {adapter.tool_spec.name!r}"
                )

    def prepare(self, tool_name: Optional[str] = None) -> Tuple[ExpertHealth, ...]:
        names = (tool_name,) if tool_name is not None else self.registry.names()
        return tuple(self.get_adapter(name).prepare() for name in names)

    def health_check(self, tool_name: Optional[str] = None) -> Tuple[ExpertHealth, ...]:
        names = (tool_name,) if tool_name is not None else self.registry.names()
        return tuple(self.get_adapter(name).health_check() for name in names)

    def get_adapter(self, tool_name: str) -> ExpertAdapter:
        try:
            return self._adapters[tool_name]
        except KeyError as exc:
            raise KeyError(f"Unknown expert {tool_name!r}") from exc

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        invocation_id: Optional[str] = None,
    ) -> ExpertResult:
        tool = self.registry.get(tool_name)
        try:
            tool.validate_arguments(arguments)
        except ToolArgumentError:
            raise
        resolved_id = invocation_id or f"call_{uuid.uuid4().hex}"
        if not INVOCATION_ID_PATTERN.fullmatch(resolved_id):
            raise ValueError("invocation_id must be path-safe and contain at most 128 characters")
        return self.get_adapter(tool_name).predict(resolved_id, arguments)

    def shutdown(self) -> None:
        for adapter in self._adapters.values():
            adapter.shutdown()


def build_mock_runtime(registry: ToolRegistry, work_dir: str | Path) -> ExpertRuntime:
    from .mock_adapter import MockExpertAdapter

    root = Path(work_dir)
    adapters: Dict[str, ExpertAdapter] = {
        tool.name: MockExpertAdapter(tool_spec=tool, work_dir=root / tool.name)
        for tool in registry.tools
    }
    return ExpertRuntime(registry=registry, adapters=adapters)


def build_remote_runtime(
    registry: ToolRegistry,
    base_url: str,
    work_dir: str | Path,
    timeout_seconds: float = 600.0,
    api_prefix: str = "/v1",
) -> ExpertRuntime:
    from .remote_adapter import RemoteExpertAdapter

    root = Path(work_dir)
    adapters: Dict[str, ExpertAdapter] = {
        tool.name: RemoteExpertAdapter(
            tool_spec=tool,
            work_dir=root / tool.name,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            api_prefix=api_prefix,
        )
        for tool in registry.tools
    }
    return ExpertRuntime(registry=registry, adapters=adapters)


def overlay_remote_tools(
    runtime: ExpertRuntime,
    tool_base_urls: Mapping[str, str],
    work_dir: str | Path,
    timeout_seconds: float = 600.0,
    api_prefix: str = "/v1",
) -> ExpertRuntime:
    """Replace selected local adapters with per-tool Expert Worker clients."""
    from .remote_adapter import RemoteExpertAdapter

    unknown = sorted(set(tool_base_urls) - set(runtime.registry.names()))
    if unknown:
        raise ExpertConfigurationError(f"Remote overlays reference unknown tools: {unknown}")
    root = Path(work_dir)
    adapters: Dict[str, ExpertAdapter] = {}
    for tool in runtime.registry.tools:
        base_url = tool_base_urls.get(tool.name)
        adapters[tool.name] = (
            RemoteExpertAdapter(
                tool_spec=tool,
                work_dir=root / tool.name,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
                api_prefix=api_prefix,
            )
            if base_url
            else runtime.get_adapter(tool.name)
        )
    return ExpertRuntime(registry=runtime.registry, adapters=adapters)


def load_expert_runtime(
    path: str | Path,
    registry: ToolRegistry,
    work_dir: str | Path | None = None,
) -> ExpertRuntime:
    from .mock_adapter import MockExpertAdapter

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ExpertConfigurationError("Expert runtime config must contain an object")
    if str(payload.get("schema_version", "")).strip() != "1.0":
        raise ExpertConfigurationError("Expert runtime config requires schema_version '1.0'")
    raw_experts = payload.get("experts")
    if not isinstance(raw_experts, dict):
        raise ExpertConfigurationError("Expert runtime config requires an experts object")

    if work_dir is not None:
        root = Path(work_dir).resolve()
    else:
        root = Path(str(payload.get("work_dir", "runs/expert_runtime")))
        if not root.is_absolute():
            root = (config_path.parent / root).resolve()

    adapters: Dict[str, ExpertAdapter] = {}
    for tool_name, raw_config in raw_experts.items():
        if not isinstance(raw_config, dict):
            raise ExpertConfigurationError(f"experts.{tool_name} must be an object")
        enabled = raw_config.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ExpertConfigurationError(f"experts.{tool_name}.enabled must be a boolean")
        try:
            tool = registry.get(str(tool_name))
        except KeyError as exc:
            if not enabled:
                continue
            raise ExpertConfigurationError(f"Unknown configured expert {tool_name!r}") from exc
        backend = str(raw_config.get("backend", "")).strip()
        if backend not in {
            "mock",
            "geometry_numpy",
            "gufnet_3d_inference",
            "pointcept_ptv3_inference",
            "pointcept_semantic_inference",
            "hydro_program3d_inference",
            "rfanet_change_detection",
            "deterministic_quality_verification",
        }:
            raise ExpertConfigurationError(
                f"experts.{tool_name}.backend {backend!r} is not implemented"
            )
        adapter_class = MockExpertAdapter
        if backend == "geometry_numpy":
            from .geometry_adapter import GeometryRelationAdapter

            if tool.name != "geometry_relation_analysis":
                raise ExpertConfigurationError(
                    "backend 'geometry_numpy' can only serve geometry_relation_analysis"
                )
            adapter_class = GeometryRelationAdapter
        adapter_kwargs: Dict[str, Any] = {}
        if backend == "hydro_program3d_inference":
            from .hydro_program3d_adapter import HydroProgram3DAdapter

            if tool.name != "language_guided_point_segmentation":
                raise ExpertConfigurationError(
                    "backend 'hydro_program3d_inference' can only serve language_guided_point_segmentation"
                )
            adapter_class = HydroProgram3DAdapter
            checkpoint_value = raw_config.get("checkpoint_path")
            if not isinstance(checkpoint_value, str) or not checkpoint_value.strip():
                raise ExpertConfigurationError(
                    f"experts.{tool_name}.checkpoint_path must be a non-empty path"
                )
            checkpoint_path = Path(checkpoint_value)
            if not checkpoint_path.is_absolute():
                checkpoint_path = (config_path.parent / checkpoint_path).resolve()
            adapter_kwargs["checkpoint_path"] = checkpoint_path
            geometry_value = raw_config.get("geometry_root")
            if isinstance(geometry_value, str) and geometry_value.strip():
                geometry_path = Path(geometry_value)
                if not geometry_path.is_absolute():
                    geometry_path = (config_path.parent / geometry_path).resolve()
                adapter_kwargs["geometry_root"] = geometry_path
            adapter_kwargs["device"] = str(raw_config.get("device", "cuda:0"))
            adapter_kwargs["geometry_split"] = str(raw_config.get("geometry_split", "test"))
            adapter_kwargs["max_points"] = raw_config.get("max_points")
            adapter_kwargs["image_size"] = raw_config.get("image_size")
            adapter_kwargs["mask_threshold"] = float(raw_config.get("mask_threshold", 0.5))
            raw_mask_thresholds = raw_config.get("mask_thresholds", {})
            if not isinstance(raw_mask_thresholds, dict):
                raise ExpertConfigurationError(
                    f"experts.{tool_name}.mask_thresholds must be an object"
                )
            adapter_kwargs["mask_thresholds"] = {
                str(name): float(value) for name, value in raw_mask_thresholds.items()
            }
            for field_name in (
                "no_target_posterior_threshold",
                "no_target_probability_max_threshold",
            ):
                value = raw_config.get(field_name)
                adapter_kwargs[field_name] = float(value) if value is not None else None
            adapter_kwargs["compiler_backend"] = str(raw_config.get("compiler_backend", "rule"))
        if backend == "deterministic_quality_verification":
            from .quality_verification_adapter import QualityVerificationAdapter

            if tool.name != "result_quality_verification":
                raise ExpertConfigurationError(
                    "backend 'deterministic_quality_verification' can only serve result_quality_verification"
                )
            adapter_class = QualityVerificationAdapter
        if backend == "rfanet_change_detection":
            from .change_detection_adapter import ChangeDetectionAdapter

            if tool.name != "image_change_detection":
                raise ExpertConfigurationError(
                    "backend 'rfanet_change_detection' can only serve image_change_detection"
                )
            adapter_class = ChangeDetectionAdapter
            for field_name in ("checkpoint_path", "vendor_root"):
                value = raw_config.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    raise ExpertConfigurationError(
                        f"experts.{tool_name}.{field_name} must be a non-empty path"
                    )
                resolved_path = Path(value)
                if not resolved_path.is_absolute():
                    resolved_path = (config_path.parent / resolved_path).resolve()
                adapter_kwargs[field_name] = resolved_path
            adapter_kwargs["device"] = str(raw_config.get("device", "cuda:0"))
            adapter_kwargs["input_size"] = int(raw_config.get("input_size", 256))
        if backend == "gufnet_3d_inference":
            from .gufnet_adapter import MultimodalGufnetAdapter, PointGufnetAdapter

            if tool.name not in {
                "point_semantic_segmentation",
                "multimodal_semantic_segmentation",
            }:
                raise ExpertConfigurationError(
                    "backend 'gufnet_3d_inference' can only serve GUFNet segmentation tools"
                )
            adapter_class = (
                MultimodalGufnetAdapter
                if tool.name == "multimodal_semantic_segmentation"
                else PointGufnetAdapter
            )
            for field_name in ("checkpoint_path", "config_path", "vendor_root"):
                value = raw_config.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    raise ExpertConfigurationError(
                        f"experts.{tool_name}.{field_name} must be a non-empty path"
                    )
                resolved_path = Path(value)
                if not resolved_path.is_absolute():
                    resolved_path = (config_path.parent / resolved_path).resolve()
                adapter_kwargs[field_name] = resolved_path
            adapter_kwargs["device"] = str(raw_config.get("device", "cuda:0"))
            adapter_kwargs["max_chunk_points"] = int(raw_config.get("max_chunk_points", 100_000))
            adapter_kwargs["min_chunk_points"] = int(raw_config.get("min_chunk_points", 12_500))
        if backend in {"pointcept_ptv3_inference", "pointcept_semantic_inference"}:
            from .pointcept_adapter import PointceptPtv3Adapter

            if tool.name != "point_semantic_segmentation":
                raise ExpertConfigurationError(
                    f"backend {backend!r} can only serve point_semantic_segmentation"
                )
            adapter_class = PointceptPtv3Adapter
            adapter_kwargs["backend_name"] = backend
            adapter_kwargs["model_family"] = str(
                raw_config.get("model_family", "PointTransformerV3")
            )
            for field_name in ("checkpoint_path", "config_path", "vendor_root"):
                value = raw_config.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    raise ExpertConfigurationError(
                        f"experts.{tool_name}.{field_name} must be a non-empty path"
                    )
                resolved_path = Path(value)
                if not resolved_path.is_absolute():
                    resolved_path = (config_path.parent / resolved_path).resolve()
                adapter_kwargs[field_name] = resolved_path
            adapter_kwargs["device"] = str(raw_config.get("device", "cuda:0"))
            adapter_kwargs["split"] = str(raw_config.get("split", "test"))
            split_root_value = raw_config.get("split_root")
            if split_root_value is not None:
                if not isinstance(split_root_value, str) or not split_root_value.strip():
                    raise ExpertConfigurationError(
                        f"experts.{tool_name}.split_root must be a non-empty path"
                    )
                split_root_path = Path(split_root_value)
                if not split_root_path.is_absolute():
                    split_root_path = (config_path.parent / split_root_path).resolve()
                adapter_kwargs["split_root"] = split_root_path
            raw_python_paths = raw_config.get("python_paths", [])
            if not isinstance(raw_python_paths, list) or not all(
                isinstance(value, str) and value.strip() for value in raw_python_paths
            ):
                raise ExpertConfigurationError(
                    f"experts.{tool_name}.python_paths must be a list of non-empty paths"
                )
            resolved_python_paths = []
            for value in raw_python_paths:
                resolved_path = Path(value)
                if not resolved_path.is_absolute():
                    resolved_path = (config_path.parent / resolved_path).resolve()
                resolved_python_paths.append(resolved_path)
            adapter_kwargs["python_paths"] = resolved_python_paths
            cache_value = raw_config.get("prediction_cache_dir")
            if isinstance(cache_value, str) and cache_value.strip():
                cache_path = Path(cache_value)
                if not cache_path.is_absolute():
                    cache_path = (config_path.parent / cache_path).resolve()
                adapter_kwargs["prediction_cache_dir"] = cache_path
            write_cache_value = raw_config.get("prediction_write_cache_dir")
            if isinstance(write_cache_value, str) and write_cache_value.strip():
                write_cache_path = Path(write_cache_value)
                if not write_cache_path.is_absolute():
                    write_cache_path = (config_path.parent / write_cache_path).resolve()
                adapter_kwargs["prediction_write_cache_dir"] = write_cache_path
            cache_zero_based = raw_config.get("cache_labels_zero_based", True)
            if not isinstance(cache_zero_based, bool):
                raise ExpertConfigurationError(
                    f"experts.{tool_name}.cache_labels_zero_based must be a boolean"
                )
            adapter_kwargs["cache_labels_zero_based"] = cache_zero_based
        adapters[str(tool_name)] = adapter_class(
            tool_spec=tool,
            work_dir=root / str(tool_name),
            enabled=enabled,
            **adapter_kwargs,
        )
    return ExpertRuntime(registry=registry, adapters=adapters)
