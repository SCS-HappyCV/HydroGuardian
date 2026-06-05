# 用于准备 hydro-program3d SceneTensorSample 输入的 LangGraph 节点。
# 本节点只处理状态流转；文件读取、demo 构造、校验和 trace 摘要都放在
# scene_samples/ 中，保持职责拆分清楚。

from __future__ import annotations

from clients.file_assets import FileAssetError
from clients.scene_manifest import SceneManifestServiceError, get_scene_manifest
from config import (
    ALLOW_DEMO_SCENE_SAMPLE,
    SCENE_MANIFEST_DIR,
    SCENE_MANIFEST_SERVICE_ENABLED,
    SCENE_SAMPLE_DIR,
)
from scene_samples import (
    LoadedSceneSample,
    SceneManifestLoadError,
    SceneSampleLoadError,
    SceneSampleValidationError,
    build_demo_scene_sample,
    load_scene_sample_from_manifest,
    load_scene_sample_from_manifest_payload,
    load_scene_sample_from_disk,
    summarize_scene_sample,
    validate_scene_sample,
)
from state import AgentState, append_error, append_trace


# 按优先级解析样本来源：先查入库 manifest，再读本地 manifest / 样本，最后按配置回退到 demo 样本。
async def _load_scene_sample(state: AgentState) -> LoadedSceneSample | None:
    if SCENE_MANIFEST_SERVICE_ENABLED:
        manifest_payload = await get_scene_manifest(state["scene_id"])
        if manifest_payload is not None:
            return await load_scene_sample_from_manifest_payload(state, manifest_payload)
    loaded = await load_scene_sample_from_manifest(state, SCENE_MANIFEST_DIR)
    if loaded is not None:
        return loaded
    loaded = load_scene_sample_from_disk(state, SCENE_SAMPLE_DIR)
    if loaded is not None:
        return loaded
    if ALLOW_DEMO_SCENE_SAMPLE:
        return LoadedSceneSample(sample=build_demo_scene_sample(state), source="demo")
    return None


# 准备并校验后续 3D 执行要使用的场景张量样本。
async def scene_data_adapter_node(state: AgentState) -> AgentState:
    # 如果前面已经明确 abstain / review，且连 program 都没有生成，
    # 这里就不再继续做样本准备，避免无意义的后续调用。
    if state["status"] in {"ABSTAINED", "REVIEW_REQUIRED"} and not state["selected_program"]:
        return state

    try:
        loaded = await _load_scene_sample(state)
    except SceneManifestLoadError as exc:
        state["status"] = "FAILED"
        append_error(
            state,
            "prepare_scene_sample.manifest",
            "failed to load scene asset manifest",
            {"path": str(exc.path), "reason": exc.reason},
        )
        return state
    except SceneManifestServiceError as exc:
        state["status"] = "FAILED"
        append_error(
            state,
            "prepare_scene_sample.manifest_service",
            "failed to query scene asset manifest",
            {"reason": str(exc)},
        )
        return state
    except FileAssetError as exc:
        state["status"] = "FAILED"
        append_error(
            state,
            "prepare_scene_sample.asset",
            "failed to resolve scene file asset",
            {"reason": str(exc)},
        )
        return state
    except SceneSampleLoadError as exc:
        state["status"] = "FAILED"
        append_error(
            state,
            "prepare_scene_sample.load",
            "failed to load scene tensor sample",
            {"path": str(exc.path), "reason": exc.reason},
        )
        return state

    if loaded is None:
        # 真实环境里如果走到这里，通常说明 scene_id 对不上样本，
        # 或者预处理产物根本还没准备好。
        state["status"] = "FAILED"
        append_error(
            state,
            "prepare_scene_sample",
            "missing scene tensor sample",
            {
                "scene_manifest_dir": str(SCENE_MANIFEST_DIR),
                "scene_sample_dir": str(SCENE_SAMPLE_DIR),
            },
        )
        return state

    # 先生成摘要再校验，这样无效样本也能在 errors 中留下足够诊断信息。
    summary = summarize_scene_sample(
        loaded.sample,
        source=loaded.source,
        source_path=loaded.source_path,
    )
    try:
        validate_scene_sample(loaded.sample)
    except SceneSampleValidationError as exc:
        state["status"] = "FAILED"
        append_error(
            state,
            "prepare_scene_sample.validate",
            "invalid scene tensor sample",
            {"issues": exc.issues, "summary": summary},
        )
        return state

    # 只有校验通过的样本才写入共享状态，后续节点无需猜测
    # scene_tensor_sample 是否真的可执行。
    state["scene_tensor_sample"] = loaded.sample
    # 到这里后，后面的 3D 执行节点就拿到了完整输入。
    state["status"] = "SCENE_SAMPLE_READY"
    append_trace(
        state,
        "prepare_scene_sample",
        "scene sample prepared",
        summary,
    )
    return state
