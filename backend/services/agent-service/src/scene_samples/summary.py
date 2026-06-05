# 场景样本摘要辅助模块。
# 摘要会写入 AgentState.trace，让运维和调试人员无需展开大张量也能看到
# 当前请求实际使用了什么样本。

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


# 在不引入 numpy 或 torch 的情况下，从 JSON 数组推断嵌套 shape。
def infer_shape(value: Any, max_depth: int = 5) -> list[int]:
    shape: list[int] = []
    current = value
    for _ in range(max_depth):
        if not isinstance(current, list):
            break
        shape.append(len(current))
        if not current:
            break
        current = current[0]
    return shape


# 构建适合 trace/debug 响应的小型非张量摘要。
def summarize_scene_sample(
    sample: Dict[str, Any],
    *,
    source: str,
    source_path: Path | None = None,
) -> Dict[str, Any]:
    points_shape = infer_shape(sample.get("points_xyz"))
    mask_shape = infer_shape(sample.get("valid_point_mask"))
    geometry_shape = infer_shape(sample.get("point_geometry_features"))
    metadata = sample.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    source_files = metadata.get("source_files") or sample.get("source_files")
    if not isinstance(source_files, dict):
        source_files = {}

    # 对 [N,3] 点张量，len(shape) 为 2；对 [B,N,3]，len(shape) 为 3。
    point_count = points_shape[-2] if len(points_shape) >= 2 else 0
    batch_size = points_shape[0] if len(points_shape) == 3 else 1
    geometry_feature_dim = geometry_shape[-1] if len(geometry_shape) >= 2 else 0

    # 该对象可能经由 gRPC 和 HTTP debug 输出传递，必须保持小而清晰。
    summary: Dict[str, Any] = {
        "source": source,
        "sample_id": sample.get("sample_id", ""),
        "is_demo_sample": bool(metadata.get("is_demo_sample")),
        "image_shape": infer_shape(sample.get("images")),
        "points_xyz_shape": points_shape,
        "points_rgb_shape": infer_shape(sample.get("points_rgb")),
        "geometry_feature_shape": geometry_shape,
        "valid_point_mask_shape": mask_shape,
        "point_count": point_count,
        "batch_size": batch_size,
        "geometry_feature_dim": geometry_feature_dim,
        "has_pre_image": bool(sample.get("pre_image_path") or sample.get("pre_image_url")),
        "has_post_image": bool(sample.get("post_image_path") or sample.get("post_image_url")),
        "preprocess_version": metadata.get("preprocess_version", ""),
        "checksum_sha256": metadata.get("checksum_sha256", ""),
        "source_file_roles": sorted(source_files.keys()),
    }
    if source_files:
        summary["source_files"] = {
            role: {
                "fileId": info.get("fileId", ""),
                "objectKey": info.get("objectKey", ""),
                "fileType": info.get("fileType", ""),
                "checksumSha256": info.get("checksumSha256", ""),
            }
            for role, info in source_files.items()
            if isinstance(info, dict)
        }
    if source_path is not None:
        summary["source_path"] = str(source_path)
    return summary
