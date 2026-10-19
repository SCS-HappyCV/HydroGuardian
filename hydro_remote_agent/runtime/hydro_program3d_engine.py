from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

import numpy as np


def infer_program_task_type(program: Dict[str, Any]) -> str:
    if program.get("relations"):
        return "relation"
    steps = list(program.get("steps") or [])
    if any(str(step.get("op", "")).lower() == "relate" for step in steps):
        return "relation"
    if program.get("attributes"):
        return "attribute"
    if any(str(step.get("op", "")).lower() in {"filter_attribute", "attribute"} for step in steps):
        return "attribute"
    return "class"


def should_calibrate_no_target(
    inferred_task_type: str,
    posterior_no_target_mass: float,
    probability_max: float,
    posterior_threshold: float | None,
    probability_max_threshold: float | None,
) -> bool:
    return bool(
        posterior_threshold is not None
        and probability_max_threshold is not None
        and inferred_task_type == "class"
        and posterior_no_target_mass >= posterior_threshold
        and probability_max <= probability_max_threshold
    )


@dataclass(frozen=True)
class HydroProgram3DPrediction:
    target_mask: np.ndarray
    target_probabilities: np.ndarray
    sample_indices: np.ndarray
    compiled_program: Dict[str, Any]
    selected_program: Dict[str, Any]
    num_source_points: int
    num_sampled_points: int
    execution_confidence: float
    abstained: bool
    no_target: bool
    device: str
    geometry_used: bool
    selected_candidate_index: int = 0
    candidate_posterior_scores: tuple[float, ...] = ()
    candidate_active_mask: tuple[bool, ...] = ()
    posterior_no_target_mass: float = 0.0
    abstain_probability: float = 0.0
    inferred_task_type: str = "class"
    applied_mask_threshold: float = 0.5
    model_no_target: bool = False
    calibrated_no_target: bool = False
    preview_positions: Optional[np.ndarray] = None
    preview_colors: Optional[np.ndarray] = None
    preview_indices: Optional[np.ndarray] = None
    preview_bounds: Optional[np.ndarray] = None


def visualization_preview_indices(
    target_mask: np.ndarray,
    base_budget: int = 240_000,
    target_budget: int = 120_000,
) -> np.ndarray:
    count = int(target_mask.shape[0])
    if count <= 0:
        return np.empty(0, dtype=np.uint32)
    base_count = min(count, max(1, int(base_budget)))
    base = np.linspace(0, count - 1, num=base_count, dtype=np.int64)
    targets = np.flatnonzero(target_mask)
    if not len(targets) or target_budget <= 0:
        return base.astype(np.uint32, copy=False)
    selected_target_count = min(len(targets), int(target_budget))
    target_positions = np.linspace(0, len(targets) - 1, num=selected_target_count, dtype=np.int64)
    return np.unique(np.concatenate((base, targets[target_positions]))).astype(np.uint32, copy=False)


class HydroProgram3DInferenceEngine:
    """Source-coordinate inference wrapper for HydroProgram3D."""

    def __init__(
        self,
        checkpoint_path: str | Path,
        device: str = "cuda:0",
        geometry_root: str | Path | None = None,
        geometry_split: str = "test",
        max_points: int | None = None,
        image_size: int | None = None,
        mask_threshold: float = 0.5,
        mask_thresholds: Dict[str, float] | None = None,
        no_target_posterior_threshold: float | None = None,
        no_target_probability_max_threshold: float | None = None,
        sampling_seed: int = 42,
        compiler_backend: str = "rule",
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.device_name = str(device)
        self.geometry_root = Path(geometry_root) if geometry_root else None
        self.geometry_split = str(geometry_split)
        self.max_points_override = max_points
        self.image_size_override = image_size
        self.mask_threshold = float(mask_threshold)
        self.mask_thresholds = {
            str(name): float(value) for name, value in (mask_thresholds or {}).items()
        }
        for name, value in self.mask_thresholds.items():
            if name not in {"class", "attribute", "relation"}:
                raise ValueError(f"Unsupported mask threshold task type: {name}")
            if not 0.0 < value < 1.0:
                raise ValueError(f"mask_thresholds.{name} must be between 0 and 1")
        self.no_target_posterior_threshold = (
            float(no_target_posterior_threshold)
            if no_target_posterior_threshold is not None
            else None
        )
        self.no_target_probability_max_threshold = (
            float(no_target_probability_max_threshold)
            if no_target_probability_max_threshold is not None
            else None
        )
        self.sampling_seed = int(sampling_seed)
        self.compiler_backend = str(compiler_backend)
        self.initialized = False
        self.model: Any = None
        self.compiler: Any = None
        self.config: Dict[str, Any] = {}
        self.device: Any = None

    @property
    def max_points(self) -> int:
        return int(self.max_points_override or self.config.get("max_points", 131072))

    @property
    def image_size(self) -> int:
        return int(self.image_size_override or self.config.get("image_size", 512))

    def prepare(self) -> None:
        if self.initialized:
            return
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(f"Missing HydroProgram3D checkpoint: {self.checkpoint_path}")
        import torch

        from hydro_program3d.query_program import HydrologicalQueryCompiler, QueryCompilerConfig
        from hydro_program3d.runtime import load_checkpoint_model

        self.device = torch.device(self.device_name)
        self.model, _, self.config = load_checkpoint_model(
            str(self.checkpoint_path), self.device
        )
        self.model.eval()
        compiler_config = QueryCompilerConfig(
            backend=self.compiler_backend,
            program_schema_mode=str(self.config.get("program_schema_mode", "field")),
            program_version=str(self.config.get("program_version", "v3_operatorized")),
            num_program_candidates=int(self.config.get("num_program_candidates", 3)),
            enable_program_repair=not bool(self.config.get("disable_program_repair", False)),
            enable_no_target_option=bool(self.config.get("enable_no_target_option", True)),
        )
        self.compiler = HydrologicalQueryCompiler(config=compiler_config)
        self.initialized = True

    def _geometry_features(self, sample_id: str, num_points: int) -> tuple[Any, bool]:
        import torch

        feature_dim = int(self.config.get("geometry_feature_dim", 4))
        if self.geometry_root is None:
            configured_root = self.config.get("geometry_root")
            root = Path(configured_root) if configured_root else None
        else:
            root = self.geometry_root
        candidates = [] if root is None else [
            root / self.geometry_split / f"{sample_id}.pt",
            root / f"{sample_id}.pt",
        ]
        cache_path = next((path for path in candidates if path.is_file()), None)
        if cache_path is None:
            return torch.zeros((num_points, feature_dim), dtype=torch.float32), False
        payload = torch.load(cache_path, map_location="cpu")
        features = payload["geometry_features"].float().detach()
        if tuple(features.shape) != (num_points, feature_dim):
            raise ValueError(
                f"Geometry cache shape mismatch for {sample_id}: "
                f"{tuple(features.shape)} != {(num_points, feature_dim)}"
            )
        return features, True

    def _sample_indices(self, num_points: int) -> np.ndarray:
        if num_points <= self.max_points:
            return np.arange(num_points, dtype=np.int64)
        generator = np.random.default_rng(self.sampling_seed)
        return np.sort(
            generator.choice(num_points, size=self.max_points, replace=False).astype(np.int64)
        )

    @staticmethod
    def _interpolate_probabilities(
        source_xyz: np.ndarray,
        sampled_xyz: np.ndarray,
        sampled_probabilities: np.ndarray,
    ) -> np.ndarray:
        if len(source_xyz) == len(sampled_xyz):
            return sampled_probabilities.astype(np.float32, copy=True)
        try:
            from scipy.spatial import cKDTree
        except ImportError as exc:
            raise RuntimeError(
                "scipy is required to map sampled predictions to the source point cloud"
            ) from exc
        tree = cKDTree(sampled_xyz)
        _, nearest = tree.query(source_xyz, k=1, workers=-1)
        return sampled_probabilities[np.asarray(nearest, dtype=np.int64)].astype(
            np.float32, copy=False
        )

    def predict(
        self,
        image_path: str | Path,
        point_cloud_path: str | Path,
        query: str,
    ) -> HydroProgram3DPrediction:
        if not self.initialized:
            raise RuntimeError("HydroProgram3D inference engine is not prepared")
        import torch

        from wcs_unified.dataset import load_image_tensor, load_point_tensor

        image_path = Path(image_path)
        point_cloud_path = Path(point_cloud_path)
        if not image_path.is_file():
            raise FileNotFoundError(f"Missing image: {image_path}")
        if not point_cloud_path.is_file():
            raise FileNotFoundError(f"Missing point cloud: {point_cloud_path}")
        query = str(query).strip()
        if not query:
            raise ValueError("query must not be empty")

        points = load_point_tensor(str(point_cloud_path))
        if points.shape[0] == 0:
            raise ValueError(f"Point cloud is empty: {point_cloud_path}")
        source_xyz = points[:, :3].numpy()
        centered_xyz = points[:, :3] - points[:, :3].mean(dim=0, keepdim=True)
        rgb = points[:, 3:6] / 255.0
        region_id = point_cloud_path.parent.parent.name
        sample_id = f"{region_id}_{point_cloud_path.stem}" if region_id else point_cloud_path.stem
        geometry, geometry_used = self._geometry_features(sample_id, len(points))
        sample_indices = self._sample_indices(len(points))
        index_tensor = torch.from_numpy(sample_indices)

        bundle = self.compiler.compile_text_bundle(query, scene_context=None)
        bundle_payload = bundle.to_dict()
        image = load_image_tensor(str(image_path), self.image_size).unsqueeze(0).to(self.device)
        xyz_batch = centered_xyz[index_tensor].unsqueeze(0).to(self.device)
        rgb_batch = rgb[index_tensor].unsqueeze(0).to(self.device)
        geometry_batch = geometry[index_tensor].unsqueeze(0).to(self.device)
        valid_mask = torch.ones(
            (1, len(sample_indices)), dtype=torch.bool, device=self.device
        )
        with torch.inference_mode():
            outputs = self.model(
                images=image,
                points_xyz=xyz_batch,
                points_rgb=rgb_batch,
                point_geometry_features=geometry_batch,
                program_bundles=[bundle_payload],
                texts=[query],
                valid_point_mask=valid_mask,
                output_mode="inference",
            )

        sampled_probabilities = torch.sigmoid(outputs["mask_logits"])[0].float().cpu().numpy()
        probabilities = self._interpolate_probabilities(
            source_xyz,
            source_xyz[sample_indices],
            sampled_probabilities,
        )
        selected_candidate_index = int(outputs.get("selected_candidate_idx", [0])[0])
        model_no_target = bool(outputs.get("selected_candidate_is_no_target", [False])[0])
        abstained = bool(outputs.get("abstain_mask", [False])[0])

        confidence_value = outputs.get("execution_confidence")
        execution_confidence = (
            float(confidence_value[0].float().cpu()) if confidence_value is not None else 0.0
        )
        selected_programs = outputs.get("selected_program_dicts") or []
        selected_program = dict(selected_programs[0]) if selected_programs else {}
        candidate_count = len(bundle_payload.get("candidates", []))
        posterior_tensor = outputs.get("candidate_posterior_scores")
        candidate_posterior_scores = (
            tuple(float(value) for value in posterior_tensor[0, :candidate_count].float().cpu().tolist())
            if posterior_tensor is not None
            else ()
        )
        active_tensor = outputs.get("candidate_active_mask")
        candidate_active_mask = (
            tuple(bool(value) for value in active_tensor[0, :candidate_count].bool().cpu().tolist())
            if active_tensor is not None
            else ()
        )
        no_target_indices = []
        for index, candidate in enumerate(bundle_payload.get("candidates", [])):
            candidate_metadata = dict(candidate.get("metadata") or {})
            program_metadata = dict((candidate.get("program") or {}).get("metadata") or {})
            if candidate_metadata.get("no_target_candidate") or program_metadata.get("no_target_candidate"):
                no_target_indices.append(index)
        posterior_no_target_mass = sum(
            candidate_posterior_scores[index]
            for index in no_target_indices
            if index < len(candidate_posterior_scores)
        )
        abstain_tensor = outputs.get("abstain_logits")
        abstain_probability = (
            float(torch.sigmoid(abstain_tensor[0]).float().cpu())
            if abstain_tensor is not None
            else max(0.0, min(1.0, 1.0 - execution_confidence))
        )
        inferred_task_type = infer_program_task_type(selected_program)
        applied_mask_threshold = self.mask_thresholds.get(
            inferred_task_type, self.mask_threshold
        )
        probability_max = float(probabilities.max())
        calibrated_no_target = should_calibrate_no_target(
            inferred_task_type=inferred_task_type,
            posterior_no_target_mass=posterior_no_target_mass,
            probability_max=probability_max,
            posterior_threshold=self.no_target_posterior_threshold,
            probability_max_threshold=self.no_target_probability_max_threshold,
        )
        no_target = bool(model_no_target or calibrated_no_target)
        mask = probabilities >= applied_mask_threshold
        if no_target:
            mask[:] = False
        preview_indices = visualization_preview_indices(mask)
        preview_positions = source_xyz[preview_indices].astype(np.float32, copy=True)
        preview_colors = np.clip(
            rgb.numpy()[preview_indices] * 255.0,
            0,
            255,
        ).astype(np.uint8, copy=False)
        preview_bounds = np.asarray(
            [
                source_xyz[:, 0].min(), source_xyz[:, 1].min(), source_xyz[:, 2].min(),
                source_xyz[:, 0].max(), source_xyz[:, 1].max(), source_xyz[:, 2].max(),
            ],
            dtype=np.float64,
        )
        return HydroProgram3DPrediction(
            target_mask=mask.astype(np.bool_, copy=False),
            target_probabilities=probabilities,
            sample_indices=sample_indices,
            compiled_program=bundle_payload,
            selected_program=selected_program,
            num_source_points=len(points),
            num_sampled_points=len(sample_indices),
            execution_confidence=execution_confidence,
            abstained=abstained,
            no_target=no_target,
            device=str(self.device),
            geometry_used=geometry_used,
            selected_candidate_index=selected_candidate_index,
            candidate_posterior_scores=candidate_posterior_scores,
            candidate_active_mask=candidate_active_mask,
            posterior_no_target_mass=float(posterior_no_target_mass),
            abstain_probability=abstain_probability,
            inferred_task_type=inferred_task_type,
            applied_mask_threshold=float(applied_mask_threshold),
            model_no_target=model_no_target,
            calibrated_no_target=calibrated_no_target,
            preview_positions=preview_positions,
            preview_colors=preview_colors,
            preview_indices=preview_indices,
            preview_bounds=preview_bounds,
        )

    def shutdown(self) -> None:
        self.model = None
        self.compiler = None
        self.initialized = False
        try:
            import torch

            if str(self.device_name).startswith("cuda") and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


class HydroProgram3DEnginePool:
    _engines: Dict[tuple[str, ...], HydroProgram3DInferenceEngine] = {}
    _lock = Lock()

    @classmethod
    def get(cls, **kwargs: Any) -> HydroProgram3DInferenceEngine:
        key = tuple(
            f"{name}={json.dumps(str(value), sort_keys=True)}"
            for name, value in sorted(kwargs.items())
        )
        with cls._lock:
            if key not in cls._engines:
                cls._engines[key] = HydroProgram3DInferenceEngine(**kwargs)
            return cls._engines[key]
