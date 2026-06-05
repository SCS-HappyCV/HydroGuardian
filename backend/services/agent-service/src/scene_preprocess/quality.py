# 场景预处理质量报告工具。
# 本模块把图像、点云、几何特征和样本校验结果整理成前端可展示的质量摘要。

from __future__ import annotations

from typing import Any, Dict

from scene_samples.summary import infer_shape

from .contract import ScenePreprocessRequest


# 构建预处理质量报告，供 HTTP 响应和 sample metadata 共同使用。
def build_quality_report(
    *,
    request: ScenePreprocessRequest,
    sample: Dict[str, Any],
    image_metadata: Dict[str, Any],
    point_cloud_payload: Dict[str, Any],
    validation_issues: list[str],
) -> Dict[str, Any]:
    point_metadata = point_cloud_payload.get("metadata", {})
    if not isinstance(point_metadata, dict):
        point_metadata = {}

    image_shape = infer_shape(sample.get("images"))
    points_shape = infer_shape(sample.get("points_xyz"))
    geometry_shape = infer_shape(sample.get("point_geometry_features"))
    mask_shape = infer_shape(sample.get("valid_point_mask"))
    warnings = _build_warnings(
        request=request,
        point_metadata=point_metadata,
        image_shape=image_shape,
        points_shape=points_shape,
        geometry_shape=geometry_shape,
        validation_issues=validation_issues,
    )

    return {
        "schemaVersion": "scene_preprocess_quality_report.v1",
        "sceneId": request.scene_id,
        "sampleId": request.resolved_sample_id(),
        "preprocessVersion": request.resolved_preprocess_version(),
        "imageShape": image_shape,
        "pointsShape": points_shape,
        "pointsRgbShape": infer_shape(sample.get("points_rgb")),
        "geometryFeatureShape": geometry_shape,
        "validPointMaskShape": mask_shape,
        "pointCountOriginal": int(point_metadata.get("point_count_original", 0)),
        "pointCountSampled": int(point_metadata.get("point_count_sampled", 0)),
        "maxPoints": request.resolved_max_points(),
        "imageSize": image_metadata.get("image_size", request.resolved_image_size()),
        "geometryFeatureNames": point_metadata.get("geometry_feature_names", []),
        "geometryCellSize": point_metadata.get("geometry_cell_size", 0.0),
        "hasRgb": bool(point_metadata.get("has_rgb", False)),
        "hasPreImage": bool(request.pre_image_file_id),
        "hasPostImage": bool(request.post_image_file_id),
        "sampleValidation": {
            "valid": not validation_issues,
            "issues": validation_issues,
        },
        "warnings": warnings,
    }


# 将质量报告写入样本 metadata，便于后续 case 快照和排障回放。
def attach_quality_report(sample: Dict[str, Any], quality_report: Dict[str, Any]) -> None:
    metadata = sample.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["quality_report"] = quality_report
    sample["metadata"] = metadata


# 根据预处理结果生成可读 warning，不阻断样本上传。
def _build_warnings(
    *,
    request: ScenePreprocessRequest,
    point_metadata: Dict[str, Any],
    image_shape: list[int],
    points_shape: list[int],
    geometry_shape: list[int],
    validation_issues: list[str],
) -> list[str]:
    warnings: list[str] = []
    point_count_original = int(point_metadata.get("point_count_original", 0))
    point_count_sampled = int(point_metadata.get("point_count_sampled", 0))

    if point_count_sampled < 64:
        warnings.append("point cloud has fewer than 64 sampled points")
    if point_count_original > request.resolved_max_points():
        warnings.append("point cloud was downsampled to max_points")
    if not point_metadata.get("has_rgb", False):
        warnings.append("point cloud RGB was not detected; default gray color was used")
    if not request.pre_image_file_id or not request.post_image_file_id:
        warnings.append("pre/post image file ids are incomplete; change detection may be skipped")
    if len(image_shape) != 3:
        warnings.append("image tensor shape is not [3,H,W]")
    if len(points_shape) != 2:
        warnings.append("point tensor shape is not [N,3]")
    if len(geometry_shape) == 2 and geometry_shape[-1] != 4:
        warnings.append("geometry feature dimension is not 4")
    warnings.extend(f"sample validation issue: {issue}" for issue in validation_issues)
    return warnings
