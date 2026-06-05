# SceneTensorSample 校验器。
# 本模块在 agent 调用 hydro-program3d 前守住输入边界，让坏样本以清晰的
# agent 错误失败，而不是拖到模型服务里变成 500。

from __future__ import annotations

from typing import Any, Dict

from .summary import infer_shape


# 当场景样本违反最小 /execute 张量契约时抛出。
class SceneSampleValidationError(ValueError):
    # 将所有问题集中保存，便于调用方返回一个结构化错误。
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("; ".join(issues))


# 这些字段是 hydro-program3d 所需的最小张量输入。
REQUIRED_TENSOR_FIELDS = [
    "images",
    "points_xyz",
    "points_rgb",
    "point_geometry_features",
    "valid_point_mask",
]


# 校验 manifest 来源样本必须携带可追溯资产元数据。
def _validate_manifest_metadata(sample: Dict[str, Any], issues: list[str]) -> None:
    metadata = sample.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    if metadata.get("agent_sample_source") != "manifest":
        return

    if not isinstance(sample.get("sample_id"), str) or not sample.get("sample_id"):
        issues.append("manifest sample must have sample_id")
    if not (isinstance(sample.get("scene_id"), str) and sample.get("scene_id")) and not metadata.get("scene_id"):
        issues.append("manifest sample must have scene_id")
    if not metadata.get("preprocess_version"):
        issues.append("manifest sample metadata.preprocess_version is required")
    source_files = metadata.get("source_files") or sample.get("source_files")
    if not isinstance(source_files, dict) or not source_files:
        issues.append("manifest sample source_files is required")
    else:
        scene_sample = source_files.get("scene_sample")
        if not isinstance(scene_sample, dict) or not scene_sample.get("fileId"):
            issues.append("manifest sample source_files.scene_sample.fileId is required")
    checksum = metadata.get("checksum_sha256")
    if not isinstance(checksum, str) or len(checksum) != 64:
        issues.append("manifest sample metadata.checksum_sha256 must be a SHA-256 hex string")


# 将 [N,D] 和 [B,N,D] 点张量归一成可比较的 (B,N) 布局。
def _point_layout(shape: list[int], *, final_dim: int | None = None) -> tuple[int, int] | None:
    if len(shape) == 2:
        point_count, dim = shape
        batch_size = 1
    elif len(shape) == 3:
        batch_size, point_count, dim = shape
    else:
        return None

    if point_count <= 0:
        return None
    if final_dim is not None and dim != final_dim:
        return None
    if final_dim is None and dim <= 0:
        return None
    return batch_size, point_count


# 将 [N] 和 [B,N] mask 归一成与点张量一致的 (B,N) 布局。
def _mask_layout(shape: list[int]) -> tuple[int, int] | None:
    if len(shape) == 1:
        return 1, shape[0]
    if len(shape) == 2:
        return shape[0], shape[1]
    return None


# 校验下游执行器接受的两种图像布局。
def _validate_image_shape(shape: list[int], issues: list[str]) -> None:
    if len(shape) == 3 and shape[0] == 3 and shape[1] > 0 and shape[2] > 0:
        return
    if len(shape) == 4 and shape[1] == 3 and shape[0] > 0 and shape[2] > 0 and shape[3] > 0:
        return
    issues.append("images must have shape [3,H,W] or [B,3,H,W]")


# 在发送到 hydro-program3d /execute 前校验场景样本。
def validate_scene_sample(sample: Dict[str, Any]) -> None:
    issues: list[str] = []
    if not isinstance(sample, dict):
        raise SceneSampleValidationError(["sample must be a JSON object"])

    # 必需字段缺失或不是数组时先失败；shape 推断依赖 list 结构。
    missing = [field for field in REQUIRED_TENSOR_FIELDS if field not in sample]
    if missing:
        issues.append(f"missing required tensor fields: {', '.join(missing)}")

    for field in REQUIRED_TENSOR_FIELDS:
        if field in sample and not isinstance(sample[field], list):
            issues.append(f"{field} must be a JSON array")

    if issues:
        raise SceneSampleValidationError(issues)

    _validate_manifest_metadata(sample, issues)

    # 这里有意只做结构性 shape 检查；数值 dtype/range 检查应放到正式预处理服务中。
    image_shape = infer_shape(sample["images"])
    points_shape = infer_shape(sample["points_xyz"])
    rgb_shape = infer_shape(sample["points_rgb"])
    geometry_shape = infer_shape(sample["point_geometry_features"])
    mask_shape = infer_shape(sample["valid_point_mask"])

    _validate_image_shape(image_shape, issues)

    points_layout = _point_layout(points_shape, final_dim=3)
    if points_layout is None:
        issues.append("points_xyz must have shape [N,3] or [B,N,3]")

    rgb_layout = _point_layout(rgb_shape, final_dim=3)
    if rgb_layout is None:
        issues.append("points_rgb must have shape [N,3] or [B,N,3]")

    geometry_layout = _point_layout(geometry_shape)
    if geometry_layout is None:
        issues.append("point_geometry_features must have shape [N,G] or [B,N,G]")

    mask_layout = _mask_layout(mask_shape)
    if mask_layout is None:
        issues.append("valid_point_mask must have shape [N] or [B,N]")

    # 执行器会按索引组合所有点级数组，因此 RGB、几何特征和 valid mask 的
    # batch/点数必须与 points_xyz 一致。
    if points_layout is not None:
        for name, layout in [
            ("points_rgb", rgb_layout),
            ("point_geometry_features", geometry_layout),
            ("valid_point_mask", mask_layout),
        ]:
            if layout is not None and layout != points_layout:
                issues.append(
                    f"{name} layout {layout} must match points_xyz layout {points_layout}"
                )

    if issues:
        raise SceneSampleValidationError(issues)
