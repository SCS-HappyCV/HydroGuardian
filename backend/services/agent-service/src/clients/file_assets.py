# file-service 资产客户端。
# 本模块专门负责查询和下载 file-service 中的文件资产，避免 case 持久化客户端继续膨胀。

from __future__ import annotations

import json
from json import JSONDecodeError
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


# file-service 查询或下载失败时抛出该异常，调用方负责写入 AgentState.errors。
class FileAssetError(RuntimeError):
    pass


# 将 file-service 的 FileReply 转成 agent-service 内部统一字典。
def file_reply_to_dict(reply: file_pb2.FileReply) -> Dict[str, Any]:
    return {
        "fileId": reply.file_id,
        "fileName": reply.file_name,
        "contentType": reply.content_type,
        "size": reply.size,
        "downloadUrl": reply.download_url,
        "objectKey": reply.object_key,
        "fileType": reply.file_type,
        "checksumSha256": reply.checksum_sha256,
    }


# 查询 file-service 中的文件元数据。
async def get_file_info(file_id: str) -> Dict[str, Any]:
    if not file_id:
        raise FileAssetError("file_id is required")
    request = file_pb2.GetFileRequest(file_id=file_id)
    try:
        target = await resolve_grpc_target(FILE_SERVICE_NAME, FILE_GRPC_ADDR)
        async with grpc_client.open_channel(target, max_message_bytes=FILE_GRPC_MAX_MESSAGE_BYTES) as channel:
            stub = file_pb2_grpc.FileRpcServiceStub(channel)
            reply = await stub.GetFile(request, timeout=FILE_GRPC_TIMEOUT_SECONDS)
        return file_reply_to_dict(reply)
    except Exception as exc:
        raise FileAssetError(f"failed to query file asset {file_id}: {exc}") from exc


# 下载 file-service 中的文件内容，并同时返回文件元数据。
async def download_file(file_id: str) -> tuple[Dict[str, Any], bytes]:
    if not file_id:
        raise FileAssetError("file_id is required")
    request = file_pb2.GetFileRequest(file_id=file_id)
    try:
        target = await resolve_grpc_target(FILE_SERVICE_NAME, FILE_GRPC_ADDR)
        async with grpc_client.open_channel(target, max_message_bytes=FILE_GRPC_MAX_MESSAGE_BYTES) as channel:
            stub = file_pb2_grpc.FileRpcServiceStub(channel)
            reply = await stub.DownloadFile(request, timeout=FILE_GRPC_TIMEOUT_SECONDS)
        return file_reply_to_dict(reply.file), bytes(reply.content)
    except Exception as exc:
        raise FileAssetError(f"failed to download file asset {file_id}: {exc}") from exc


# 下载并解析 JSON 文件资产，主要用于 SceneTensorSample。
async def download_json_file(file_id: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    file_info, content = await download_file(file_id)
    try:
        payload = json.loads(content.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise FileAssetError(f"file {file_id} is not valid UTF-8 JSON") from exc
    except JSONDecodeError as exc:
        raise FileAssetError(f"file {file_id} is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise FileAssetError(f"file {file_id} JSON root must be an object")
    return file_info, payload
