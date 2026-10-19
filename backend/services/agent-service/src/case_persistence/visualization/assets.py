# 可视化资产引用构建工具。
# 本模块只整理 file-service 返回的轻量元数据，不下载文件，也不保存大数组。
from __future__ import annotations

from typing import Any, Dict


FILE_ASSET_FIELDS = (
    "fileId",
    "fileName",
    "contentType",
    "size",
    "downloadUrl",
    "objectKey",
    "fileType",
    "checksumSha256",
)


# 安全返回字典，避免外部字段类型不稳定时污染快照。
def as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


# 从 sample 中提取 metadata；SceneTensorSample 的预处理信息都挂在这里。
def sample_metadata(sample: Dict[str, Any]) -> Dict[str, Any]:
    return as_dict(sample.get("metadata"))


# 从 sample 或 metadata 中提取 source_files，兼容 manifest 加载和预处理直出两种结构。
def sample_source_files(sample: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    metadata = sample_metadata(sample)
    source_files = metadata.get("source_files") or sample.get("source_files")
    if not isinstance(source_files, dict):
        return {}
    return {
        str(role): as_dict(info)
        for role, info in source_files.items()
        if isinstance(info, dict)
    }


# 压缩 file-service 文件元数据，只保留前端展示和二次查询需要的字段。
def compact_file_asset(file_info: Dict[str, Any]) -> Dict[str, Any]:
    if not file_info:
        return {}
    return {
        field: file_info.get(field, "")
        for field in FILE_ASSET_FIELDS
        if field in file_info
    }


# 构建主图像或正射图资产信息，供二维风险叠加视图使用。
def build_ortho_asset(sample: Dict[str, Any]) -> Dict[str, Any]:
    metadata = sample_metadata(sample)
    source_files = sample_source_files(sample)
    image_metadata = as_dict(metadata.get("image_preprocess"))
    image_size = int(image_metadata.get("image_size") or 0)

    return {
        "schema_version": "ortho_visualization.v1",
        "source_file": compact_file_asset(source_files.get("image", {})),
        "original_width": int(image_metadata.get("original_width") or 0),
        "original_height": int(image_metadata.get("original_height") or 0),
        "display_width": image_size,
        "display_height": image_size,
        "coordinate_mode": "resized_pixel_inferred_from_normalized_xy",
        "projection_status": "inferred_from_point_cloud_xy",
        "projection_warning": (
            "current MVP has no georeferenced orthophoto transform; "
            "risk boxes are inferred from normalized point-cloud XY"
        ),
    }


# 构建前后影像对比资产；当前 mask 可能尚未上传，因此 mask 字段保持可选。
def build_change_comparison_asset(sample: Dict[str, Any], change_pack: Dict[str, Any]) -> Dict[str, Any]:
    source_files = sample_source_files(sample)
    pre_image = compact_file_asset(source_files.get("pre_image", {}))
    post_image = compact_file_asset(source_files.get("post_image", {}))
    mask_file = _change_mask_asset(change_pack)

    return {
        "schema_version": "change_comparison_visualization.v1",
        "status": change_pack.get("status", ""),
        "change_type": change_pack.get("change_type", ""),
        "change_score": change_pack.get("change_score"),
        "change_summary": change_pack.get("change_summary", ""),
        "review_required": bool(change_pack.get("review_required", False)),
        "pre_image": pre_image,
        "post_image": post_image,
        "change_mask": mask_file,
        "can_compare": bool(pre_image and post_image),
        "mask_available": bool(mask_file),
        "alignment_status": "source_pair_only",
    }


# 构建变化检测 mask 文件引用；后续 change-detection 上传 mask 后可以直接复用这些字段。
def _change_mask_asset(change_pack: Dict[str, Any]) -> Dict[str, Any]:
    file_id = (
        change_pack.get("change_mask_file_id")
        or change_pack.get("mask_file_id")
        or change_pack.get("maskFileId")
    )
    download_url = (
        change_pack.get("change_mask_download_url")
        or change_pack.get("mask_download_url")
        or change_pack.get("maskDownloadUrl")
    )
    if not file_id and not download_url:
        return {}
    return {
        "fileId": file_id or "",
        "downloadUrl": download_url or "",
        "contentType": change_pack.get("mask_content_type", "image/png"),
        "fileType": "change_mask",
    }


# 构建点云源资产和预处理元数据，供 Three.js 视图选择渲染模式。
def build_point_cloud_asset(sample: Dict[str, Any]) -> Dict[str, Any]:
    metadata = sample_metadata(sample)
    source_files = sample_source_files(sample)
    point_metadata = as_dict(metadata.get("point_cloud_preprocess"))
    normalization = as_dict(point_metadata.get("normalization"))
    points_xyz = sample.get("points_xyz")

    return {
        "schema_version": "point_cloud_visualization.v1",
        "source_file": compact_file_asset(source_files.get("point_cloud", {})),
        "scene_sample_file": compact_file_asset(source_files.get("scene_sample", {})),
        "coordinate_mode": "normalized_scene_tensor",
        "point_count_original": int(point_metadata.get("point_count_original") or 0),
        "point_count_sampled": int(point_metadata.get("point_count_sampled") or _point_count(points_xyz)),
        "has_rgb": bool(point_metadata.get("has_rgb", False)),
        "geometry_feature_names": point_metadata.get("geometry_feature_names", []),
        "geometry_cell_size": point_metadata.get("geometry_cell_size", 0.0),
        "normalization": normalization,
        "bounds_normalized": _bounds_from_points(points_xyz),
        "render_hint": {
            "preferred_source": "scene_sample_file",
            "preferred_format": "json_points_xyz_rgb",
            "point_size": 0.018,
        },
    }


# 统计点数量；这里只读外层长度，不把点数组写入快照。
def _point_count(points_xyz: Any) -> int:
    if isinstance(points_xyz, list):
        return len(points_xyz)
    return 0


# 从归一化点坐标中计算轻量边界框，便于 Three.js 初始化相机。
def _bounds_from_points(points_xyz: Any) -> Dict[str, list[float]]:
    if not isinstance(points_xyz, list) or not points_xyz:
        return {}
    valid_points = [
        point
        for point in points_xyz
        if isinstance(point, list) and len(point) >= 3
    ]
    if not valid_points:
        return {}

    # 只计算 min/max，避免把完整点云复制进快照。
    xs = [float(point[0]) for point in valid_points]
    ys = [float(point[1]) for point in valid_points]
    zs = [float(point[2]) for point in valid_points]
    return {
        "min": [round(min(xs), 6), round(min(ys), 6), round(min(zs), 6)],
        "max": [round(max(xs), 6), round(max(ys), 6), round(max(zs), 6)],
    }
