# 场景预处理请求与结果结构。
# 这些结构把 gRPC 字段和内部处理逻辑解耦，便于后续拆成独立服务。

from __future__ import annotations

from dataclasses import dataclass

from config import (
    SCENE_PREPROCESS_IMAGE_SIZE,
    SCENE_PREPROCESS_MAX_POINTS,
    SCENE_PREPROCESS_VERSION,
)


# 场景预处理的通用异常。
class ScenePreprocessError(RuntimeError):
    pass


# 入参校验失败时抛出，gRPC 层会映射为 INVALID_ARGUMENT。
class ScenePreprocessValidationError(ScenePreprocessError):
    pass


# 场景预处理请求。
@dataclass(frozen=True)
class ScenePreprocessRequest:
    scene_id: str
    sample_id: str
    image_file_id: str
    point_cloud_file_id: str
    pre_image_file_id: str = ""
    post_image_file_id: str = ""
    preprocess_version: str = ""
    image_size: int = 0
    max_points: int = 0

    # 返回归一化后的 sample_id；为空时使用 scene_id。
    def resolved_sample_id(self) -> str:
        return self.sample_id or self.scene_id

    # 返回归一化后的预处理版本。
    def resolved_preprocess_version(self) -> str:
        return self.preprocess_version or SCENE_PREPROCESS_VERSION

    # 返回实际使用的图像尺寸。
    def resolved_image_size(self) -> int:
        return self.image_size if self.image_size > 0 else SCENE_PREPROCESS_IMAGE_SIZE

    # 返回实际使用的最大点数。
    def resolved_max_points(self) -> int:
        return self.max_points if self.max_points > 0 else SCENE_PREPROCESS_MAX_POINTS

    # 校验请求最小必填项和数值边界。
    def validate(self) -> None:
        if not self.scene_id:
            raise ScenePreprocessValidationError("scene_id is required")
        if not self.image_file_id:
            raise ScenePreprocessValidationError("image_file_id is required")
        if not self.point_cloud_file_id:
            raise ScenePreprocessValidationError("point_cloud_file_id is required")
        if self.resolved_image_size() < 8 or self.resolved_image_size() > 1024:
            raise ScenePreprocessValidationError("image_size must be between 8 and 1024")
        if self.resolved_max_points() < 1 or self.resolved_max_points() > 200000:
            raise ScenePreprocessValidationError("max_points must be between 1 and 200000")


# 场景预处理完成后的结果。
@dataclass(frozen=True)
class ScenePreprocessResult:
    scene_id: str
    sample_id: str
    scene_sample_file_id: str
    image_file_id: str
    point_cloud_file_id: str
    pre_image_file_id: str
    post_image_file_id: str
    preprocess_version: str
    manifest_registered: bool
    checksum_sha256: str
    scene_sample_file_name: str
    status: str = "SCENE_SAMPLE_READY"
