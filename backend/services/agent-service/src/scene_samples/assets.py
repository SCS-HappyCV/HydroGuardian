# 基于 file-service 资产清单加载 SceneTensorSample。
# 本模块把 manifest、file-service 查询和样本元数据补齐集中到一起。

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from clients.file_assets import download_json_file, get_file_info
from state import AgentState

from .loader import LoadedSceneSample
from .manifest import SceneAssetManifest, load_scene_manifest_from_disk, normalize_scene_manifest_payload


# 查询 manifest 中引用的所有文件资产元数据。
async def _resolve_source_files(manifest: SceneAssetManifest) -> Dict[str, Dict[str, Any]]:
    source_files: Dict[str, Dict[str, Any]] = {}
    for role, file_id in manifest.asset_file_ids().items():
        if role == "scene_sample":
            continue
        source_files[role] = await get_file_info(file_id)
    return source_files


# 补齐 sample 中供后续节点和 case 快照使用的来源元数据。
def _attach_manifest_metadata(
    *,
    sample: Dict[str, Any],
    state: AgentState,
    manifest: SceneAssetManifest,
    manifest_source: str,
    scene_sample_file: Dict[str, Any],
    source_files: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    sample.setdefault("scene_id", manifest.scene_id)
    sample.setdefault("sample_id", manifest.sample_id)
    sample.setdefault("text", state["selected_program"].get("source_text", state["task_text"]))
    sample.setdefault("program", state["selected_program"])

    source_files = {"scene_sample": scene_sample_file, **source_files}
    sample["source_files"] = source_files

    metadata = sample.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.update(
        {
            "agent_sample_source": "manifest",
            "manifest_source": manifest_source,
            "is_demo_sample": False,
            "scene_id": manifest.scene_id,
            "sample_id": manifest.sample_id,
            "manifest_schema_version": manifest.schema_version,
            "manifest_path": str(manifest.source_path) if manifest.source_path is not None else "",
            "preprocess_version": manifest.preprocess_version,
            "manifest_created_at": manifest.created_at,
            "manifest_checksum_sha256": manifest.checksum_sha256,
            "checksum_sha256": scene_sample_file.get("checksumSha256", ""),
            "source_files": source_files,
        }
    )
    sample["metadata"] = metadata

    # 变化检测节点可以直接使用这些 URL，而不用理解 manifest 结构。
    if "pre_image" in source_files:
        sample.setdefault("pre_image_file_id", source_files["pre_image"].get("fileId", ""))
        sample.setdefault("pre_image_url", source_files["pre_image"].get("downloadUrl", ""))
    if "post_image" in source_files:
        sample.setdefault("post_image_file_id", source_files["post_image"].get("fileId", ""))
        sample.setdefault("post_image_url", source_files["post_image"].get("downloadUrl", ""))

    return sample


# 按 manifest 从 file-service 下载 SceneTensorSample JSON。
async def load_scene_sample_from_manifest(
    state: AgentState,
    manifest_dir: Path,
) -> LoadedSceneSample | None:
    manifest = load_scene_manifest_from_disk(state, manifest_dir)
    if manifest is None:
        return None
    scene_sample_file, sample = await download_json_file(manifest.scene_sample_file_id)
    source_files = await _resolve_source_files(manifest)
    sample = _attach_manifest_metadata(
        sample=sample,
        state=state,
        manifest=manifest,
        manifest_source="disk",
        scene_sample_file=scene_sample_file,
        source_files=source_files,
    )
    return LoadedSceneSample(
        sample=sample,
        source="manifest",
        source_path=manifest.source_path,
        manifest=manifest.raw,
    )


# 按 case-service 返回的 manifest 字典下载 SceneTensorSample JSON。
async def load_scene_sample_from_manifest_payload(
    state: AgentState,
    payload: Dict[str, Any],
) -> LoadedSceneSample:
    manifest = normalize_scene_manifest_payload(payload, state)
    scene_sample_file, sample = await download_json_file(manifest.scene_sample_file_id)
    source_files = await _resolve_source_files(manifest)
    sample = _attach_manifest_metadata(
        sample=sample,
        state=state,
        manifest=manifest,
        manifest_source="case-service",
        scene_sample_file=scene_sample_file,
        source_files=source_files,
    )
    return LoadedSceneSample(
        sample=sample,
        source="manifest_service",
        source_path=None,
        manifest=manifest.raw,
    )
