# file-service 文件上传客户端。
# 本模块负责把 agent-service 生成的样本 JSON 等派生产物上传回 file-service/MinIO。

from __future__ import annotations

from typing import Any, Dict

import grpc_client
from config import (
    FILE_GRPC_ADDR,
    FILE_GRPC_MAX_MESSAGE_BYTES,
    FILE_GRPC_TIMEOUT_SECONDS,
    FILE_SERVICE_NAME,
)
from discovery import resolve_grpc_target
from generated import file_pb2, file_pb2_grpc

from .file_assets import FileAssetError, file_reply_to_dict


# 上传一份文件资产，并返回 file-service 的标准文件元数据字典。
async def upload_file_asset(
    *,
    file_name: str,
    content_type: str,
    content: bytes,
    file_type: str,
) -> Dict[str, Any]:
    if not file_name or not file_name.strip():
        raise FileAssetError("file_name is required")
    if not content:
        raise FileAssetError("upload content is required")

    request = file_pb2.UploadFileRequest(
        file_name=file_name.strip(),
        content_type=content_type or "application/octet-stream",
        content=content,
        file_type=file_type or "generic",
    )
    try:
        target = await resolve_grpc_target(FILE_SERVICE_NAME, FILE_GRPC_ADDR)
        async with grpc_client.open_channel(target, max_message_bytes=FILE_GRPC_MAX_MESSAGE_BYTES) as channel:
            stub = file_pb2_grpc.FileRpcServiceStub(channel)
            reply = await stub.UploadFile(request, timeout=FILE_GRPC_TIMEOUT_SECONDS)
        return file_reply_to_dict(reply)
    except Exception as exc:
        raise FileAssetError(f"failed to upload file asset {file_name}: {exc}") from exc


# 上传 SceneTensorSample JSON，使用固定 fileType 便于后续检索和排障。
async def upload_scene_sample_json(file_name: str, content: bytes) -> Dict[str, Any]:
    return await upload_file_asset(
        file_name=file_name,
        content_type="application/json",
        content=content,
        file_type="scene_sample",
    )
