from __future__ import annotations

import json
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import numpy as np

from .adapter import ExpertAdapter
from .contracts import ExpertHealth, ExpertNotReadyError, ExpertResult, normalize_arguments


LABEL_KEYS = ("point_labels", "pred_labels", "labels", "class_labels")
ZERO_BASED_LABEL_KEYS = {"pred_labels", "class_labels"}
PROBABILITY_KEYS = ("class_probabilities", "probabilities", "class_probs", "logits")
POINT_KEYS = ("xyz", "points", "pointcloud", "data", "xyzrgb_label")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_xyz(array: Any, source: Path) -> np.ndarray:
    points = np.asarray(array)
    if points.ndim != 2 or points.shape[1] < 3:
        raise ValueError(f"Expected point array [N, >=3] in {source}, got {points.shape}")
    xyz = np.asarray(points[:, :3], dtype=np.float64)
    if not np.isfinite(xyz).all():
        raise ValueError(f"Point cloud {source} contains NaN or infinite XYZ values")
    return xyz


def _load_torch_payload(path: Path) -> Any:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(f"Loading {path.suffix} point files requires PyTorch") from exc
    return torch.load(path, map_location="cpu")


def load_point_xyz(path: str | Path) -> np.ndarray:
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
        return _as_xyz(np.column_stack((cloud.x, cloud.y, cloud.z)), point_path)
    if suffix in {".txt", ".xyz", ".pts", ".csv"}:
        delimiter = "," if suffix == ".csv" else None
        return _as_xyz(np.loadtxt(point_path, delimiter=delimiter, ndmin=2), point_path)
    if suffix == ".npy":
        return _as_xyz(np.load(point_path, allow_pickle=False), point_path)
    if suffix == ".npz":
        with np.load(point_path, allow_pickle=False) as payload:
            for key in POINT_KEYS:
                if key in payload:
                    return _as_xyz(payload[key], point_path)
        raise ValueError(f"Point NPZ {point_path} has none of the supported keys {POINT_KEYS}")
    if suffix in {".pt", ".pth"}:
        payload = _load_torch_payload(point_path)
        if hasattr(payload, "detach"):
            return _as_xyz(payload.detach().cpu().numpy(), point_path)
        if isinstance(payload, dict):
            for key in POINT_KEYS:
                value = payload.get(key)
                if hasattr(value, "detach"):
                    return _as_xyz(value.detach().cpu().numpy(), point_path)
        raise TypeError(f"Unsupported Torch point payload in {point_path}")
    raise ValueError(f"Unsupported point-cloud format {suffix!r}: {point_path}")


def _labels_from_array(array: Any, source: Path) -> np.ndarray:
    labels = np.atleast_1d(np.asarray(array))
    if labels.ndim == 2 and labels.shape[1] == 1:
        labels = labels[:, 0]
    if labels.ndim != 1:
        raise ValueError(f"Expected labels [N] in {source}, got {labels.shape}")
    if not np.issubdtype(labels.dtype, np.integer):
        if not np.isfinite(labels).all() or not np.equal(labels, np.floor(labels)).all():
            raise ValueError(f"Labels in {source} must contain finite integers")
    return np.asarray(labels, dtype=np.int32)


def _labels_from_named_array(key: str, array: Any, source: Path) -> np.ndarray:
    labels = _labels_from_array(array, source)
    if key in ZERO_BASED_LABEL_KEYS:
        labels = labels + 1
    return labels


def _labels_from_probabilities(array: Any, source: Path) -> np.ndarray:
    probabilities = np.asarray(array)
    if probabilities.ndim != 2 or probabilities.shape[1] < 1:
        raise ValueError(f"Expected class probabilities [N, C] in {source}, got {probabilities.shape}")
    if not np.isfinite(probabilities).all():
        raise ValueError(f"Class probabilities in {source} contain NaN or infinite values")
    return np.asarray(probabilities.argmax(axis=1) + 1, dtype=np.int32)


def load_segmentation_labels(path: str | Path) -> np.ndarray:
    result_path = Path(path)
    if not result_path.is_file():
        raise FileNotFoundError(f"Missing segmentation result: {result_path}")
    suffix = result_path.suffix.lower()
    if suffix == ".json":
        with result_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"Segmentation JSON {result_path} must contain an object")
        artifacts = payload.get("artifacts")
        if isinstance(artifacts, dict) and isinstance(artifacts.get("point_labels"), str):
            return load_segmentation_labels(artifacts["point_labels"])
        for key in LABEL_KEYS:
            if key in payload:
                return _labels_from_named_array(key, payload[key], result_path)
        raise ValueError(
            f"Segmentation JSON {result_path} is neither a result manifest nor an inline label file"
        )
    if suffix == ".npy":
        array = np.load(result_path, allow_pickle=False)
        return _labels_from_array(array, result_path)
    if suffix == ".npz":
        with np.load(result_path, allow_pickle=False) as payload:
            for key in LABEL_KEYS:
                if key in payload:
                    return _labels_from_named_array(key, payload[key], result_path)
            for key in PROBABILITY_KEYS:
                if key in payload:
                    return _labels_from_probabilities(payload[key], result_path)
        raise ValueError(
            f"Segmentation NPZ {result_path} has no supported label or probability array"
        )
    if suffix in {".txt", ".csv"}:
        delimiter = "," if suffix == ".csv" else None
        return _labels_from_array(np.loadtxt(result_path, delimiter=delimiter), result_path)
    if suffix in {".pt", ".pth"}:
        payload = _load_torch_payload(result_path)
        if hasattr(payload, "detach"):
            return _labels_from_array(payload.detach().cpu().numpy(), result_path)
        if isinstance(payload, dict):
            for key in LABEL_KEYS:
                value = payload.get(key)
                if hasattr(value, "detach"):
                    return _labels_from_named_array(
                        key, value.detach().cpu().numpy(), result_path
                    )
            for key in PROBABILITY_KEYS:
                value = payload.get(key)
                if hasattr(value, "detach"):
                    return _labels_from_probabilities(value.detach().cpu().numpy(), result_path)
        raise TypeError(f"Unsupported Torch segmentation payload in {result_path}")
    raise ValueError(f"Unsupported segmentation format {suffix!r}: {result_path}")


def _minimum_distances(query: np.ndarray, reference: np.ndarray) -> np.ndarray:
    if len(query) == 0:
        return np.empty(0, dtype=np.float64)
    if len(reference) == 0:
        return np.full(len(query), np.inf, dtype=np.float64)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            from scipy.spatial import cKDTree

        distances, _ = cKDTree(reference).query(query, k=1, workers=-1)
        return np.asarray(distances, dtype=np.float64)
    except Exception:
        max_pairs = 2_000_000
        chunk_size = max(1, max_pairs // max(len(reference), 1))
        distances = np.empty(len(query), dtype=np.float64)
        for start in range(0, len(query), chunk_size):
            stop = min(start + chunk_size, len(query))
            delta = query[start:stop, None, :] - reference[None, :, :]
            squared = np.einsum("ijk,ijk->ij", delta, delta)
            distances[start:stop] = np.sqrt(squared.min(axis=1))
        return distances


def _finite_stats(values: np.ndarray) -> Dict[str, Optional[float]]:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return {"minimum": None, "maximum": None, "mean": None, "median": None}
    return {
        "minimum": float(finite.min()),
        "maximum": float(finite.max()),
        "mean": float(finite.mean()),
        "median": float(np.median(finite)),
    }


def _region_stats(xyz: np.ndarray, mask: np.ndarray) -> Dict[str, Any]:
    points = xyz[mask]
    if len(points) == 0:
        return {
            "point_count": 0,
            "point_ratio": 0.0,
            "centroid_xyz": None,
            "bbox_min_xyz": None,
            "bbox_max_xyz": None,
            "elevation": _finite_stats(np.empty(0)),
        }
    return {
        "point_count": int(len(points)),
        "point_ratio": float(len(points) / max(len(xyz), 1)),
        "centroid_xyz": points.mean(axis=0).tolist(),
        "bbox_min_xyz": points.min(axis=0).tolist(),
        "bbox_max_xyz": points.max(axis=0).tolist(),
        "elevation": _finite_stats(points[:, 2]),
    }


def execute_geometry_operation(
    xyz: np.ndarray,
    labels: np.ndarray,
    arguments: Mapping[str, Any],
) -> Tuple[np.ndarray, Dict[str, Any], Dict[str, np.ndarray]]:
    if len(xyz) != len(labels):
        raise ValueError(
            f"Point/label count mismatch: point cloud has {len(xyz)} points, labels have {len(labels)}"
        )
    operation = str(arguments["operation"])
    target_class_id = int(arguments["target_class_id"])
    target_mask = labels == target_class_id
    reference_class_id = arguments.get("reference_class_id")
    reference_mask = (
        labels == int(reference_class_id)
        if reference_class_id is not None
        else np.zeros(len(labels), dtype=bool)
    )
    report: Dict[str, Any] = {
        "schema_version": "1.0",
        "operation": operation,
        "label_space": "raw_class_id_1_to_15",
        "num_points": int(len(xyz)),
        "target_class_id": target_class_id,
        "reference_class_id": int(reference_class_id) if reference_class_id is not None else None,
        "target": _region_stats(xyz, target_mask),
    }
    arrays: Dict[str, np.ndarray] = {}
    outcome = "result"

    if operation == "class_statistics":
        relation_mask = target_mask.copy()
        if not target_mask.any():
            outcome = "no_target"
    else:
        if reference_class_id is None:
            raise ValueError(f"operation {operation!r} requires reference_class_id")
        report["reference"] = _region_stats(xyz, reference_mask)
        if not target_mask.any():
            outcome = "no_target"
            relation_mask = np.zeros(len(labels), dtype=bool)
        elif not reference_mask.any():
            outcome = "no_reference"
            relation_mask = np.zeros(len(labels), dtype=bool)
        else:
            target_indices = np.flatnonzero(target_mask)
            target_xyz = xyz[target_mask]
            reference_xyz = xyz[reference_mask]
            horizontal_distances = _minimum_distances(target_xyz[:, :2], reference_xyz[:, :2])
            arrays["target_horizontal_distance_m"] = horizontal_distances
            report["horizontal_distance_m"] = _finite_stats(horizontal_distances)

            if operation == "near":
                threshold = float(arguments.get("distance_threshold_m", 3.0))
                selected = horizontal_distances <= threshold
                relation_mask = np.zeros(len(labels), dtype=bool)
                relation_mask[target_indices[selected]] = True
                report["distance_threshold_m"] = threshold
            elif operation == "above":
                margin = float(arguments.get("z_margin_m", 0.2))
                reference_elevation = float(np.median(reference_xyz[:, 2]))
                selected = target_xyz[:, 2] > reference_elevation + margin
                relation_mask = np.zeros(len(labels), dtype=bool)
                relation_mask[target_indices[selected]] = True
                report["z_margin_m"] = margin
                report["reference_median_elevation_m"] = reference_elevation
            elif operation == "pair_distance":
                spatial_distances = _minimum_distances(target_xyz, reference_xyz)
                arrays["target_spatial_distance_m"] = spatial_distances
                report["spatial_distance_m"] = _finite_stats(spatial_distances)
                relation_mask = target_mask.copy()
            elif operation == "elevation_difference":
                reference_elevation = float(np.median(reference_xyz[:, 2]))
                elevation_difference = target_xyz[:, 2] - reference_elevation
                arrays["target_elevation_difference_m"] = elevation_difference
                report["reference_median_elevation_m"] = reference_elevation
                report["elevation_difference_m"] = _finite_stats(elevation_difference)
                relation_mask = target_mask.copy()
            else:
                raise ValueError(f"Unsupported geometry operation {operation!r}")

    report["outcome"] = outcome
    report["result"] = _region_stats(xyz, relation_mask)
    report["selected_target_ratio"] = float(
        relation_mask.sum() / max(int(target_mask.sum()), 1)
    )
    return relation_mask, report, arrays


class GeometryRelationAdapter(ExpertAdapter):
    """Deterministic local implementation of geometry relation analysis."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, backend="geometry_numpy", **kwargs)
        self._initialized = False

    def prepare(self) -> ExpertHealth:
        if not self.enabled:
            return self.health_check()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True
        return self.health_check()

    def health_check(self) -> ExpertHealth:
        if not self.enabled:
            return ExpertHealth(
                tool=self.tool_spec.name,
                backend=self.backend,
                status="disabled",
                initialized=False,
                message="Expert is disabled by runtime configuration.",
            )
        return ExpertHealth(
            tool=self.tool_spec.name,
            backend=self.backend,
            status="ready" if self._initialized else "not_ready",
            initialized=self._initialized,
            message=(
                "Deterministic NumPy geometry expert is ready."
                if self._initialized
                else "Geometry expert has not been prepared."
            ),
            details={"is_mock": False, "operations": list(self.tool_spec.arguments_schema["properties"]["operation"]["enum"])},
        )

    def predict(self, invocation_id: str, arguments: Mapping[str, Any]) -> ExpertResult:
        if not self.enabled or not self._initialized:
            raise ExpertNotReadyError(f"Expert {self.tool_spec.name!r} is not ready")
        normalized_arguments = normalize_arguments(arguments)
        started_at = _utc_now()
        started = time.perf_counter()
        xyz = load_point_xyz(normalized_arguments["point_cloud_path"])
        labels = load_segmentation_labels(normalized_arguments["segmentation_result_path"])
        relation_mask, report, diagnostic_arrays = execute_geometry_operation(
            xyz, labels, normalized_arguments
        )

        invocation_dir = self.work_dir / invocation_id
        invocation_dir.mkdir(parents=True, exist_ok=False)
        mask_path = invocation_dir / "relation_mask.npz"
        np.savez_compressed(
            mask_path,
            relation_mask=relation_mask,
            point_indices=np.flatnonzero(relation_mask).astype(np.int64),
            **diagnostic_arrays,
        )
        report.update(
            {
                "point_cloud_path": str(Path(normalized_arguments["point_cloud_path"]).resolve()),
                "segmentation_result_path": str(
                    Path(normalized_arguments["segmentation_result_path"]).resolve()
                ),
            }
        )
        report_path = invocation_dir / "geometry_report.json"
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)

        manifest_path = invocation_dir / "manifest.json"
        result = ExpertResult(
            schema_version="1.0",
            invocation_id=invocation_id,
            tool=self.tool_spec.name,
            tool_version=self.tool_spec.version,
            backend=self.backend,
            status="succeeded",
            started_at=started_at,
            finished_at=_utc_now(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
            coordinate_space=self.tool_spec.output.coordinate_space,
            result_types=self.tool_spec.output.result_types,
            artifacts={
                "relation_mask": str(mask_path.resolve()),
                "geometry_report": str(report_path.resolve()),
            },
            manifest_path=str(manifest_path.resolve()),
            arguments=normalized_arguments,
            is_mock=False,
            metrics={
                "outcome": report["outcome"],
                "num_points": int(len(xyz)),
                "selected_points": int(relation_mask.sum()),
                "selected_target_ratio": report["selected_target_ratio"],
            },
            warnings=(
                (
                    f"Geometry analysis returned {report['outcome']}; "
                    "the relation mask is intentionally empty."
                ),
            )
            if report["outcome"] != "result"
            else (),
        )
        result.write_manifest()
        return result

    def shutdown(self) -> None:
        self._initialized = False
