# 场景资产清单 gRPC 客户端。
# agent-service 通过它从 case-service 查询已入库的 scene_id -> fileId 映射。

from __future__ import annotations

from typing import Any, Dict

import grpc

import grpc_client
from config import (
    CASE_GRPC_ADDR,
    CASE_SERVICE_NAME,
    SCENE_MANIFEST_SERVICE_TIMEOUT_SECONDS,
)
from discovery import resolve_grpc_target
from generated import case_pb2, case_pb2_grpc


# 查询场景清单失败时抛出，调用方负责决定是否失败或回退。
class SceneManifestServiceError(RuntimeError):
    pass


# 将 case-service 的 SceneManifestReply 转成 manifest 归一化函数可直接消费的字典。
def scene_manifest_reply_to_payload(reply: case_pb2.SceneManifestReply) -> Dict[str, Any]:
    return {
        "schemaVersion": reply.schema_version,
        "sceneId": reply.scene_id,
        "sampleId": reply.sample_id,
        "sceneSampleFileId": reply.scene_sample_file_id,
        "imageFileId": reply.image_file_id,
        "pointCloudFileId": reply.point_cloud_file_id,
        "preImageFileId": reply.pre_image_file_id,
        "postImageFileId": reply.post_image_file_id,
        "preprocessVersion": reply.preprocess_version,
        "checksumSha256": reply.checksum_sha256,
        "createdAt": reply.created_at,
        "updatedAt": reply.updated_at,
    }


# 按 scene_id 查询已入库的场景资产清单；不存在时返回 None 以便继续本地兜底。
async def get_scene_manifest(scene_id: str) -> Dict[str, Any] | None:
    if not scene_id or not scene_id.strip():
        raise SceneManifestServiceError("scene_id is required")

    request = case_pb2.GetSceneManifestRequest(scene_id=scene_id.strip())
    try:
        target = await resolve_grpc_target(CASE_SERVICE_NAME, CASE_GRPC_ADDR)
        async with grpc_client.open_channel(target) as channel:
            stub = case_pb2_grpc.CaseRpcServiceStub(channel)
            reply = await stub.GetSceneManifest(
                request,
                timeout=SCENE_MANIFEST_SERVICE_TIMEOUT_SECONDS,
            )
        return scene_manifest_reply_to_payload(reply)
    except grpc.aio.AioRpcError as exc:
        if exc.code() == grpc.StatusCode.NOT_FOUND:
            return None
        raise SceneManifestServiceError(f"failed to query scene manifest: {exc}") from exc
    except Exception as exc:
        raise SceneManifestServiceError(f"failed to query scene manifest: {exc}") from exc
