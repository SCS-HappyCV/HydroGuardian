from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from .adapter import ExpertAdapter
from .contracts import ExpertHealth, ExpertNotReadyError, ExpertResult, normalize_arguments
from .geometry_adapter import load_point_xyz


SEGMENTATION_TOOLS = {
    "point_semantic_segmentation",
    "multimodal_semantic_segmentation",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(
    checks: list[Dict[str, Any]],
    name: str,
    status: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    checks.append(
        {
            "name": name,
            "status": status,
            "message": message,
            "details": details or {},
        }
    )


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing JSON artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must contain an object: {path}")
    return payload


def _artifact_path(manifest: Mapping[str, Any], name: str) -> Path:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get(name), str):
        raise ValueError(f"Result manifest has no artifact {name!r}")
    path = Path(artifacts[name])
    if not path.is_file():
        raise FileNotFoundError(f"Missing result artifact {name!r}: {path}")
    return path


def _verify_segmentation(
    manifest: Mapping[str, Any],
    arguments: Mapping[str, Any],
    checks: list[Dict[str, Any]],
    measurements: Dict[str, Any],
) -> None:
    labels_path = _artifact_path(manifest, "point_labels")
    with np.load(labels_path, allow_pickle=False) as payload:
        if "point_labels" not in payload:
            raise ValueError(f"Missing point_labels array in {labels_path}")
        labels = np.asarray(payload["point_labels"])
    labels = np.atleast_1d(labels)
    labels_valid = (
        labels.ndim == 1
        and np.issubdtype(labels.dtype, np.integer)
        and bool(np.all((labels >= 1) & (labels <= 15)))
    )
    _check(
        checks,
        "label_space",
        "passed" if labels_valid else "failed",
        "Labels use raw class IDs 1-15." if labels_valid else "Labels are not a valid 1-D raw class-ID array.",
        {"shape": list(labels.shape), "dtype": str(labels.dtype)},
    )
    measurements["num_predictions"] = int(labels.size)
    if labels_valid:
        class_ids, class_counts = np.unique(labels, return_counts=True)
        measurements["class_histogram"] = {
            str(int(class_id)): int(count)
            for class_id, count in zip(class_ids, class_counts)
        }
        measurements["dominant_class_ratio"] = float(class_counts.max() / max(labels.size, 1))

    point_path_value = arguments.get("point_cloud_path")
    if isinstance(point_path_value, str) and point_path_value:
        points = load_point_xyz(point_path_value)
        count_matches = len(points) == labels.size
        _check(
            checks,
            "point_count_consistency",
            "passed" if count_matches else "failed",
            "Prediction count matches the source point cloud." if count_matches else "Prediction count differs from the source point cloud.",
            {"source_points": int(len(points)), "predictions": int(labels.size)},
        )

    artifacts = manifest.get("artifacts", {})
    probability_value = artifacts.get("class_probabilities") if isinstance(artifacts, dict) else None
    if isinstance(probability_value, str) and Path(probability_value).is_file():
        with np.load(probability_value, allow_pickle=False) as payload:
            if "class_probabilities" not in payload:
                raise ValueError(f"Missing class_probabilities array in {probability_value}")
            probabilities = np.asarray(payload["class_probabilities"])
        finite = bool(np.isfinite(probabilities).all())
        shape_valid = probabilities.ndim == 2 and probabilities.shape == (labels.size, 15)
        range_valid = finite and bool(np.all((probabilities >= 0.0) & (probabilities <= 1.0)))
        sums_valid = finite and shape_valid and bool(
            np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-4)
        )
        valid = shape_valid and range_valid and sums_valid
        _check(
            checks,
            "probability_integrity",
            "passed" if valid else "failed",
            "Class probabilities are finite, normalized, and shape-consistent." if valid else "Class probabilities are invalid or inconsistent.",
            {"shape": list(probabilities.shape), "finite": finite, "range_valid": range_valid, "row_sums_valid": sums_valid},
        )
        if valid and labels.size:
            confidence = probabilities.max(axis=1)
            mean_confidence = float(confidence.mean())
            minimum_confidence = float(arguments.get("minimum_confidence", 0.6))
            measurements["mean_confidence"] = mean_confidence
            measurements["low_confidence_ratio"] = float((confidence < minimum_confidence).mean())
            _check(
                checks,
                "confidence",
                "passed" if mean_confidence >= minimum_confidence else "warning",
                "Mean confidence meets the requested threshold." if mean_confidence >= minimum_confidence else "Mean confidence is below the requested threshold.",
                {"mean": mean_confidence, "minimum": minimum_confidence},
            )
    else:
        _check(checks, "confidence", "warning", "No class-probability artifact is available.")


def _verify_language_segmentation(
    manifest: Mapping[str, Any],
    arguments: Mapping[str, Any],
    checks: list[Dict[str, Any]],
    measurements: Dict[str, Any],
) -> None:
    mask_path = _artifact_path(manifest, "target_mask")
    with np.load(mask_path, allow_pickle=False) as payload:
        if "target_mask" not in payload:
            raise ValueError(f"Missing target_mask array in {mask_path}")
        mask = np.asarray(payload["target_mask"])
    mask_valid = mask.ndim == 1 and (
        mask.dtype == np.bool_ or bool(np.all(np.isin(mask, (0, 1))))
    )
    _check(
        checks,
        "target_mask_integrity",
        "passed" if mask_valid else "failed",
        "Target mask is a one-dimensional binary array." if mask_valid else "Target mask has an invalid shape or values.",
        {"shape": list(mask.shape), "dtype": str(mask.dtype)},
    )

    probability_path = _artifact_path(manifest, "target_probabilities")
    with np.load(probability_path, allow_pickle=False) as payload:
        if "target_probabilities" not in payload:
            raise ValueError(f"Missing target_probabilities array in {probability_path}")
        probabilities = np.asarray(payload["target_probabilities"])
    probability_valid = (
        probabilities.ndim == 1
        and probabilities.shape == mask.shape
        and bool(np.isfinite(probabilities).all())
        and bool(np.all((probabilities >= 0.0) & (probabilities <= 1.0)))
    )
    _check(
        checks,
        "probability_integrity",
        "passed" if probability_valid else "failed",
        "Target probabilities are finite, bounded, and mask-aligned." if probability_valid else "Target probabilities are invalid or misaligned.",
        {"shape": list(probabilities.shape)},
    )

    source_arguments = manifest.get("arguments", {})
    point_path_value = arguments.get("point_cloud_path")
    if not isinstance(point_path_value, str) or not point_path_value:
        point_path_value = source_arguments.get("point_cloud_path") if isinstance(source_arguments, dict) else None
    if isinstance(point_path_value, str) and point_path_value:
        source_points = load_point_xyz(point_path_value)
        count_matches = len(source_points) == mask.size
        _check(
            checks,
            "point_count_consistency",
            "passed" if count_matches else "failed",
            "Language mask count matches the source point cloud." if count_matches else "Language mask count differs from the source point cloud.",
            {"source_points": int(len(source_points)), "mask_points": int(mask.size)},
        )

    metrics = manifest.get("metrics", {})
    no_target = bool(metrics.get("no_target", False)) if isinstance(metrics, dict) else False
    abstained = bool(metrics.get("abstained", False)) if isinstance(metrics, dict) else False
    confidence = metrics.get("execution_confidence") if isinstance(metrics, dict) else None
    confidence_valid = isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0
    _check(
        checks,
        "confidence_metadata",
        "passed" if confidence_valid else "warning",
        "Execution confidence is available and bounded." if confidence_valid else "Execution confidence metadata is unavailable or invalid.",
        {"execution_confidence": confidence, "abstained": abstained, "no_target": no_target},
    )
    selected_points = int(np.count_nonzero(mask))
    measurements.update(
        num_predictions=int(mask.size),
        selected_points=selected_points,
        selected_ratio=float(selected_points / max(mask.size, 1)),
        execution_confidence=confidence,
        abstained=abstained,
        no_target=no_target,
    )
    empty_is_expected = no_target or abstained
    _check(
        checks,
        "non_empty_result",
        "passed" if selected_points > 0 or empty_is_expected else "warning",
        "Empty mask is explicitly explained by no-target or abstention." if selected_points == 0 and empty_is_expected else (
            "Target mask contains selected points." if selected_points > 0 else "Target mask is empty without no-target or abstention metadata."
        ),
    )


def _verify_change_detection(
    manifest: Mapping[str, Any],
    arguments: Mapping[str, Any],
    checks: list[Dict[str, Any]],
    measurements: Dict[str, Any],
) -> None:
    mask_path = _artifact_path(manifest, "change_mask")
    mask = np.asarray(Image.open(mask_path).convert("L"))
    binary = bool(np.all(np.isin(mask, (0, 255))))
    _check(
        checks,
        "binary_mask",
        "passed" if binary else "failed",
        "Change mask is binary." if binary else "Change mask contains non-binary values.",
        {"shape": list(mask.shape)},
    )
    probability_path = _artifact_path(manifest, "change_probability_map")
    with np.load(probability_path, allow_pickle=False) as payload:
        if "change_probability_map" not in payload:
            raise ValueError(f"Missing change_probability_map array in {probability_path}")
        probability = np.asarray(payload["change_probability_map"])
    probability_valid = (
        probability.shape == mask.shape
        and bool(np.isfinite(probability).all())
        and bool(np.all((probability >= 0.0) & (probability <= 1.0)))
    )
    _check(
        checks,
        "probability_integrity",
        "passed" if probability_valid else "failed",
        "Probability map is finite, bounded, and mask-aligned." if probability_valid else "Probability map is invalid or misaligned.",
        {"shape": list(probability.shape)},
    )
    source_image_value = arguments.get("image_path")
    if not isinstance(source_image_value, str) or not source_image_value:
        source_arguments = manifest.get("arguments", {})
        source_image_value = source_arguments.get("after_image_path") if isinstance(source_arguments, dict) else None
    if isinstance(source_image_value, str) and source_image_value:
        with Image.open(source_image_value) as source_image:
            expected_shape = (source_image.height, source_image.width)
        size_matches = mask.shape == expected_shape
        _check(
            checks,
            "image_size_consistency",
            "passed" if size_matches else "failed",
            "Outputs match the after-image pixel dimensions." if size_matches else "Outputs do not match the after-image dimensions.",
            {"image_shape": list(expected_shape), "mask_shape": list(mask.shape)},
        )
    changed_ratio = float(np.count_nonzero(mask) / max(mask.size, 1))
    measurements["changed_pixels"] = int(np.count_nonzero(mask))
    measurements["changed_ratio"] = changed_ratio
    maximum_empty_ratio = float(arguments.get("maximum_empty_ratio", 0.999))
    empty_ratio = 1.0 - changed_ratio
    _check(
        checks,
        "non_empty_result",
        "passed" if empty_ratio <= maximum_empty_ratio else "warning",
        "Change result contains selected pixels." if changed_ratio > 0 else "No changed pixels were selected; abstention is recommended.",
        {"empty_ratio": empty_ratio, "maximum_empty_ratio": maximum_empty_ratio},
    )


def _verify_geometry(
    manifest: Mapping[str, Any],
    arguments: Mapping[str, Any],
    checks: list[Dict[str, Any]],
    measurements: Dict[str, Any],
) -> None:
    mask_path = _artifact_path(manifest, "relation_mask")
    with np.load(mask_path, allow_pickle=False) as payload:
        if "relation_mask" not in payload:
            raise ValueError(f"Missing relation_mask array in {mask_path}")
        relation_mask = np.asarray(payload["relation_mask"])
    mask_valid = relation_mask.ndim == 1 and relation_mask.dtype == np.bool_
    _check(
        checks,
        "relation_mask_integrity",
        "passed" if mask_valid else "failed",
        "Relation mask is a one-dimensional boolean array." if mask_valid else "Relation mask has an invalid shape or dtype.",
        {"shape": list(relation_mask.shape), "dtype": str(relation_mask.dtype)},
    )
    point_path_value = arguments.get("point_cloud_path")
    if isinstance(point_path_value, str) and point_path_value:
        points = load_point_xyz(point_path_value)
        count_matches = len(points) == relation_mask.size
        _check(
            checks,
            "point_count_consistency",
            "passed" if count_matches else "failed",
            "Relation mask count matches the source point cloud." if count_matches else "Relation mask count differs from the source point cloud.",
            {"source_points": int(len(points)), "mask_points": int(relation_mask.size)},
        )
    report = _load_json(_artifact_path(manifest, "geometry_report"))
    measurements["selected_points"] = int(relation_mask.sum())
    measurements["selected_target_ratio"] = report.get("selected_target_ratio")


def _verify_comparison(
    manifest: Mapping[str, Any],
    comparison_path: str,
    checks: list[Dict[str, Any]],
    measurements: Dict[str, Any],
) -> None:
    comparison = _load_json(Path(comparison_path))
    try:
        first_path = _artifact_path(manifest, "point_labels")
        second_path = _artifact_path(comparison, "point_labels")
        with np.load(first_path, allow_pickle=False) as first, np.load(second_path, allow_pickle=False) as second:
            first_labels = np.asarray(first["point_labels"])
            second_labels = np.asarray(second["point_labels"])
        shape_matches = first_labels.shape == second_labels.shape
        agreement = float(np.mean(first_labels == second_labels)) if shape_matches and first_labels.size else 0.0
        measurements["comparison_agreement"] = agreement
        _check(
            checks,
            "cross_expert_consistency",
            "passed" if shape_matches and agreement >= 0.8 else "warning",
            "Comparison outputs are consistent." if shape_matches and agreement >= 0.8 else "Comparison outputs differ substantially or have different shapes.",
            {"agreement": agreement, "shape_matches": shape_matches},
        )
    except (KeyError, ValueError, FileNotFoundError) as exc:
        _check(checks, "cross_expert_consistency", "warning", f"Comparison could not be evaluated: {exc}")


def verify_result(arguments: Mapping[str, Any]) -> Dict[str, Any]:
    result_path = Path(str(arguments["result_path"]))
    manifest = _load_json(result_path)
    result_artifacts = arguments.get("result_artifacts")
    if isinstance(result_artifacts, Mapping):
        manifest = dict(manifest)
        manifest["artifacts"] = {
            str(name): str(path)
            for name, path in result_artifacts.items()
            if isinstance(path, (str, Path))
        }
    source_tool = str(arguments["source_tool"])
    checks: list[Dict[str, Any]] = []
    measurements: Dict[str, Any] = {}
    manifest_tool = manifest.get("tool")
    _check(
        checks,
        "manifest_tool",
        "passed" if manifest_tool == source_tool else "failed",
        "Manifest tool matches the requested source tool." if manifest_tool == source_tool else "Manifest tool does not match source_tool.",
        {"manifest_tool": manifest_tool, "source_tool": source_tool},
    )
    if manifest.get("status") != "succeeded":
        _check(checks, "source_status", "failed", "Source result did not succeed.")
    else:
        _check(checks, "source_status", "passed", "Source result succeeded.")
    if bool(manifest.get("is_mock")):
        _check(checks, "real_prediction", "warning", "Source result is a Mock output and cannot be quality-assessed numerically.")
    elif source_tool == "language_guided_point_segmentation":
        _verify_language_segmentation(manifest, arguments, checks, measurements)
    elif source_tool in SEGMENTATION_TOOLS:
        _verify_segmentation(manifest, arguments, checks, measurements)
    elif source_tool == "image_change_detection":
        _verify_change_detection(manifest, arguments, checks, measurements)
    elif source_tool == "geometry_relation_analysis":
        _verify_geometry(manifest, arguments, checks, measurements)
    else:
        _check(checks, "supported_source", "failed", f"Unsupported source tool {source_tool!r}.")

    comparison_path = arguments.get("comparison_result_path")
    if isinstance(comparison_path, str) and comparison_path:
        _verify_comparison(manifest, comparison_path, checks, measurements)
    statuses = [item["status"] for item in checks]
    verdict = "failed" if "failed" in statuses else "warning" if "warning" in statuses else "passed"
    quality_score = max(
        0.0,
        1.0 - 0.5 * statuses.count("failed") - 0.1 * statuses.count("warning"),
    )
    return {
        "schema_version": "1.0",
        "source_tool": source_tool,
        "source_result_path": str(result_path.resolve()),
        "verdict": verdict,
        "quality_score": quality_score,
        "abstention_recommended": verdict == "failed" or any(
            item["name"] == "non_empty_result" and item["status"] == "warning"
            for item in checks
        ),
        "checks": checks,
        "measurements": measurements,
    }


def _write_overlay(path: Path, report: Mapping[str, Any]) -> None:
    canvas = Image.new("RGB", (720, 360), "white")
    draw = ImageDraw.Draw(canvas)
    colors = {"passed": "#16835b", "warning": "#d28b13", "failed": "#c53f3f"}
    verdict = str(report["verdict"])
    draw.rectangle((0, 0, 720, 58), fill=colors[verdict])
    draw.text((20, 19), f"QUALITY VERDICT: {verdict.upper()}", fill="white")
    draw.text((20, 78), f"Source: {report['source_tool']}", fill="#20252b")
    draw.text((20, 101), f"Score: {float(report['quality_score']):.2f}", fill="#20252b")
    y_position = 138
    for item in report["checks"][:8]:
        color = colors[str(item["status"])]
        draw.rectangle((20, y_position, 34, y_position + 14), fill=color)
        draw.text((44, y_position), f"{item['name']}: {item['status']}", fill="#20252b")
        y_position += 25
    canvas.save(path)


class QualityVerificationAdapter(ExpertAdapter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, backend="deterministic_quality_verification", **kwargs)
        self._initialized = False

    def prepare(self) -> ExpertHealth:
        if not self.enabled:
            return self.health_check()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True
        return self.health_check()

    def health_check(self) -> ExpertHealth:
        if not self.enabled:
            return ExpertHealth(self.tool_spec.name, self.backend, "disabled", False, "Expert is disabled by runtime configuration.")
        return ExpertHealth(
            self.tool_spec.name,
            self.backend,
            "ready" if self._initialized else "not_ready",
            self._initialized,
            "Deterministic quality verifier is ready." if self._initialized else "Quality verifier has not been prepared.",
            {"is_mock": False, "supported_sources": sorted(SEGMENTATION_TOOLS | {"language_guided_point_segmentation", "image_change_detection", "geometry_relation_analysis"})},
        )

    def predict(self, invocation_id: str, arguments: Mapping[str, Any]) -> ExpertResult:
        if not self.enabled or not self._initialized:
            raise ExpertNotReadyError(f"Expert {self.tool_spec.name!r} is not ready")
        normalized = normalize_arguments(arguments)
        started_at = _utc_now()
        started = time.perf_counter()
        report = verify_result(normalized)
        invocation_dir = self.work_dir / invocation_id
        invocation_dir.mkdir(parents=True, exist_ok=False)
        report_path = invocation_dir / "quality_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        overlay_path = invocation_dir / "diagnostic_overlay.png"
        _write_overlay(overlay_path, report)
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
            artifacts={"quality_report": str(report_path.resolve()), "diagnostic_overlay": str(overlay_path.resolve())},
            manifest_path=str(manifest_path.resolve()),
            arguments=normalized,
            is_mock=False,
            metrics={
                "verdict": report["verdict"],
                "quality_score": report["quality_score"],
                "abstention_recommended": report["abstention_recommended"],
                "failed_checks": sum(item["status"] == "failed" for item in report["checks"]),
                "warning_checks": sum(item["status"] == "warning" for item in report["checks"]),
            },
            warnings=("Quality verification recommends abstention.",) if report["abstention_recommended"] else (),
        )
        result.write_manifest()
        return result

    def shutdown(self) -> None:
        self._initialized = False
