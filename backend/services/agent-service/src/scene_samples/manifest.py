# 场景资产清单加载器。
# manifest 负责把 scene_id 映射到 file-service 中的图像、点云和 scene_sample JSON 资产。

from __future__ import annotations

from dataclasses import dataclass
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict

from state import AgentState


# manifest 加载或结构错误时抛出，调用方会写入 AgentState.errors。
class SceneManifestLoadError(ValueError):
    # 保存路径和原因，便于错误响应带结构化排障信息。
    def __init__(self, path: Path, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


# 规范化后的场景资产清单。
@dataclass(frozen=True)
class SceneAssetManifest:
    raw: Dict[str, Any]
    source_path: Path
    schema_version: str
    scene_id: str
    sample_id: str
    scene_sample_file_id: str
    image_file_id: str
    point_cloud_file_id: str
    pre_image_file_id: str
    post_image_file_id: str
    preprocess_version: str
    created_at: str
    checksum_sha256: str

    # 返回需要查询 file-service 的资产角色和 fileId。
    def asset_file_ids(self) -> Dict[str, str]:
        return {
            role: file_id
            for role, file_id in {
                "scene_sample": self.scene_sample_file_id,
                "image": self.image_file_id,
                "point_cloud": self.point_cloud_file_id,
                "pre_image": self.pre_image_file_id,
                "post_image": self.post_image_file_id,
            }.items()
            if file_id
        }


# 从多个命名风格中取第一个非空字符串，兼容 snake_case 和 camelCase。
def _first_string(payload: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# 从 assets/files 子对象中读取指定角色的 fileId。
def _asset_file_id(payload: Dict[str, Any], role: str, *direct_keys: str) -> str:
    direct = _first_string(payload, *direct_keys)
    if direct:
        return direct
    for container_key in ("assets", "files", "source_files", "sourceFiles"):
        container = payload.get(container_key)
        if not isinstance(container, dict):
            continue
        item = container.get(role)
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            value = _first_string(item, "file_id", "fileId", "id")
            if value:
                return value
    return ""


# 将原始 JSON 清单归一化为 SceneAssetManifest。
def _normalize_manifest(payload: Dict[str, Any], path: Path, state: AgentState) -> SceneAssetManifest:
    scene_id = _first_string(payload, "scene_id", "sceneId") or state["scene_id"]
    sample_id = _first_string(payload, "sample_id", "sampleId") or state["sample_id"]
    manifest = SceneAssetManifest(
        raw=payload,
        source_path=path,
        schema_version=_first_string(payload, "schema_version", "schemaVersion") or "scene_asset_manifest.v1",
        scene_id=scene_id,
        sample_id=sample_id,
        scene_sample_file_id=_asset_file_id(
            payload,
            "scene_sample",
            "scene_sample_file_id",
            "sceneSampleFileId",
        ),
        image_file_id=_asset_file_id(payload, "image", "image_file_id", "imageFileId"),
        point_cloud_file_id=_asset_file_id(
            payload,
            "point_cloud",
            "point_cloud_file_id",
            "pointCloudFileId",
        ),
        pre_image_file_id=_asset_file_id(payload, "pre_image", "pre_image_file_id", "preImageFileId"),
        post_image_file_id=_asset_file_id(payload, "post_image", "post_image_file_id", "postImageFileId"),
        preprocess_version=_first_string(payload, "preprocess_version", "preprocessVersion"),
        created_at=_first_string(payload, "created_at", "createdAt"),
        checksum_sha256=_first_string(payload, "checksum_sha256", "checksumSha256", "checksum"),
    )
    if not manifest.scene_sample_file_id:
        raise SceneManifestLoadError(path, "scene_sample_file_id is required")
    return manifest


# 从配置目录读取 scene_id 或 sample_id 对应的资产清单。
def load_scene_manifest_from_disk(state: AgentState, manifest_dir: Path) -> SceneAssetManifest | None:
    candidates = [
        manifest_dir / f"{state['scene_id']}.json",
        manifest_dir / f"{state['sample_id']}.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except JSONDecodeError as exc:
                raise SceneManifestLoadError(path, f"invalid JSON: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise SceneManifestLoadError(path, "manifest root must be a JSON object")
            return _normalize_manifest(payload, path, state)
    return None
