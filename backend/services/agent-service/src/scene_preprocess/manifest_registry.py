# 场景资产清单注册器。
# 预处理完成后通过 case-service CreateSceneManifest 保存 scene_id 到 fileId 的映射。

from __future__ import annotations

from typing import Any, Dict

import grpc_client
from config import CASE_GRPC_ADDR, CASE_GRPC_TIMEOUT_SECONDS, CASE_SERVICE_NAME
from discovery import resolve_grpc_target
from generated import case_pb2, case_pb2_grpc

from .contract import ScenePreprocessError, ScenePreprocessRequest


# 将预处理结果注册到 case-service 的 scene_asset_manifest 表。
async def register_scene_manifest(
    *,
    request: ScenePreprocessRequest,
    scene_sample_file: Dict[str, Any],
    checksum_sha256: str,
) -> case_pb2.SceneManifestReply:
    scene_sample_file_id = str(scene_sample_file.get("fileId", ""))
    if not scene_sample_file_id:
        raise ScenePreprocessError("scene sample upload did not return fileId")

    grpc_request = case_pb2.CreateSceneManifestRequest(
        scene_id=request.scene_id,
        sample_id=request.resolved_sample_id(),
        scene_sample_file_id=scene_sample_file_id,
        image_file_id=request.image_file_id,
        point_cloud_file_id=request.point_cloud_file_id,
        pre_image_file_id=request.pre_image_file_id,
        post_image_file_id=request.post_image_file_id,
        preprocess_version=request.resolved_preprocess_version(),
        checksum_sha256=checksum_sha256,
        schema_version="scene_asset_manifest.v1",
    )
    try:
        target = await resolve_grpc_target(CASE_SERVICE_NAME, CASE_GRPC_ADDR)
        async with grpc_client.open_channel(target) as channel:
            stub = case_pb2_grpc.CaseRpcServiceStub(channel)
            return await stub.CreateSceneManifest(grpc_request, timeout=CASE_GRPC_TIMEOUT_SECONDS)
    except Exception as exc:
        raise ScenePreprocessError(f"failed to register scene manifest: {exc}") from exc
