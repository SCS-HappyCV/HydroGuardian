# 场景预处理总编排服务。
# 该模块串联 file-service 下载、图像/点云预处理、样本上传和 manifest 注册。

from __future__ import annotations

from clients.file_assets import download_file
from clients.file_upload import upload_scene_sample_json

from .contract import ScenePreprocessRequest, ScenePreprocessResult
from .image import preprocess_image_bytes
from .manifest_registry import register_scene_manifest
from .point_cloud import preprocess_point_cloud_bytes
from .sample_builder import (
    build_scene_sample_file_name,
    build_scene_tensor_sample,
    serialize_scene_sample,
)


# 执行完整场景预处理链路，并返回可供前端和后续 ExecuteTask 使用的 fileId。
async def preprocess_scene(request: ScenePreprocessRequest) -> ScenePreprocessResult:
    request.validate()

    # 先下载原始资产；预处理只依赖 fileId，不直接读取本地路径。
    image_file, image_content = await download_file(request.image_file_id)
    point_cloud_file, point_cloud_content = await download_file(request.point_cloud_file_id)

    image_tensor, image_metadata = preprocess_image_bytes(
        image_content,
        request.resolved_image_size(),
    )
    point_cloud_payload = preprocess_point_cloud_bytes(
        point_cloud_content,
        request.resolved_max_points(),
    )

    sample = build_scene_tensor_sample(
        request=request,
        image_tensor=image_tensor,
        image_metadata=image_metadata,
        point_cloud_payload=point_cloud_payload,
        image_file=image_file,
        point_cloud_file=point_cloud_file,
    )
    sample_content, checksum_sha256 = serialize_scene_sample(sample)
    sample_file_name = build_scene_sample_file_name(
        request.scene_id,
        request.resolved_sample_id(),
    )

    # 样本 JSON 上传回 file-service，之后 manifest 只保存 fileId。
    scene_sample_file = await upload_scene_sample_json(sample_file_name, sample_content)
    await register_scene_manifest(
        request=request,
        scene_sample_file=scene_sample_file,
        checksum_sha256=checksum_sha256,
    )

    return ScenePreprocessResult(
        scene_id=request.scene_id,
        sample_id=request.resolved_sample_id(),
        scene_sample_file_id=str(scene_sample_file.get("fileId", "")),
        image_file_id=request.image_file_id,
        point_cloud_file_id=request.point_cloud_file_id,
        pre_image_file_id=request.pre_image_file_id,
        post_image_file_id=request.post_image_file_id,
        preprocess_version=request.resolved_preprocess_version(),
        manifest_registered=True,
        checksum_sha256=checksum_sha256,
        scene_sample_file_name=sample_file_name,
    )
