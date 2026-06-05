# SceneTensorSample 构建工具。
# 本模块把图像、点云和元数据组装成 agent-service 校验器可接受的 JSON 样本。

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict

from .contract import ScenePreprocessRequest


# 组装完整 SceneTensorSample 字典。
def build_scene_tensor_sample(
    *,
    request: ScenePreprocessRequest,
    image_tensor: list[list[list[float]]],
    image_metadata: Dict[str, Any],
    point_cloud_payload: Dict[str, Any],
    image_file: Dict[str, Any],
    point_cloud_file: Dict[str, Any],
) -> Dict[str, Any]:
    metadata = {
        "preprocess_version": request.resolved_preprocess_version(),
        "scene_id": request.scene_id,
        "sample_id": request.resolved_sample_id(),
        "is_demo_sample": False,
        "image_preprocess": image_metadata,
        "point_cloud_preprocess": point_cloud_payload["metadata"],
        "source_files": {
            "image": image_file,
            "point_cloud": point_cloud_file,
        },
    }

    # pre/post 图像只作为变化检测引用写入 manifest 和 sample 元数据，不参与第一版 3D 张量生成。
    if request.pre_image_file_id:
        metadata["pre_image_file_id"] = request.pre_image_file_id
    if request.post_image_file_id:
        metadata["post_image_file_id"] = request.post_image_file_id

    sample = {
        "schema_version": "scene_tensor_sample.mvp.v1",
        "scene_id": request.scene_id,
        "sample_id": request.resolved_sample_id(),
        "text": "",
        "images": image_tensor,
        "points_xyz": point_cloud_payload["points_xyz"],
        "points_rgb": point_cloud_payload["points_rgb"],
        "point_geometry_features": point_cloud_payload["point_geometry_features"],
        "valid_point_mask": point_cloud_payload["valid_point_mask"],
        "metadata": metadata,
    }
    return sample


# 将样本字典序列化为稳定 JSON 字节，并返回 sha256 校验和。
def serialize_scene_sample(sample: Dict[str, Any]) -> tuple[bytes, str]:
    content = json.dumps(sample, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    checksum = hashlib.sha256(content).hexdigest()
    return content, checksum


# 构建上传到 file-service 的样本文件名。
def build_scene_sample_file_name(scene_id: str, sample_id: str) -> str:
    safe_scene_id = _safe_filename_part(scene_id)
    safe_sample_id = _safe_filename_part(sample_id)
    return f"{safe_scene_id}_{safe_sample_id}_scene_sample.json"


# 清理文件名片段，避免业务 ID 中的特殊字符影响对象存储路径。
def _safe_filename_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return normalized.strip("._") or "scene"
