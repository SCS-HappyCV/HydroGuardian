from __future__ import annotations

import json
from typing import Any, Dict

from config import ALLOW_DEMO_SCENE_SAMPLE, SCENE_SAMPLE_DIR
from state import AgentState, append_error, append_trace


def build_demo_scene_sample(state: AgentState) -> Dict[str, Any]:
    # demo sample 只用于打通链路和冒烟测试。真实执行应当从磁盘样本
    # 或上游预处理服务拿到预处理后的 tensor。
    return {
        "sample_id": state["sample_id"],
        "text": state["selected_program"].get("source_text", state["task_text"]),
        "images": [
            [[0.00, 0.10], [0.20, 0.30]],
            [[0.00, 0.10], [0.20, 0.30]],
            [[0.00, 0.10], [0.20, 0.30]],
        ],
        "points_xyz": [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.1],
            [0.0, 1.0, 0.1],
        ],
        "points_rgb": [
            [0.20, 0.30, 0.40],
            [0.21, 0.32, 0.41],
            [0.19, 0.28, 0.39],
            [0.18, 0.27, 0.38],
        ],
        "point_geometry_features": [
            [0.10, 0.00, 0.20, 0.80],
            [0.09, 0.01, 0.21, 0.78],
            [0.12, 0.02, 0.22, 0.77],
            [0.11, 0.01, 0.19, 0.79],
        ],
        "valid_point_mask": [True, True, True, True],
        "program": state["selected_program"],
    }


def load_scene_sample_from_disk(state: AgentState) -> Dict[str, Any] | None:
    # 先按 scene_id 查，sample_id 作为兜底，兼容本地 demo 阶段
    # scene 命名还不稳定的情况。
    candidates = [
        SCENE_SAMPLE_DIR / f"{state['scene_id']}.json",
        SCENE_SAMPLE_DIR / f"{state['sample_id']}.json",
    ]
    for path in candidates:
        if path.is_file():
            with path.open("r", encoding="utf-8") as handle:
                sample = json.load(handle)
            if isinstance(sample, dict):
                sample.setdefault("sample_id", state["sample_id"])
                sample.setdefault("text", state["selected_program"].get("source_text", state["task_text"]))
                sample.setdefault("program", state["selected_program"])
                return sample
    return None


def scene_data_adapter_node(state: AgentState) -> AgentState:
    # 如果前面已经明确 abstain / review，且连 program 都没有生成，
    # 这里就不再继续做样本准备，避免无意义的后续调用。
    if state["status"] in {"ABSTAINED", "REVIEW_REQUIRED"} and not state["selected_program"]:
        return state

    # 优先使用真实 tensor sample；但在数据流水线尚未接通时，
    # 仍然保留 demo 回退，方便继续调图编排和服务联通性。
    sample = load_scene_sample_from_disk(state)
    if sample is not None:
        append_trace(state, "prepare_scene_sample", "scene sample loaded from disk")
    elif ALLOW_DEMO_SCENE_SAMPLE:
        sample = build_demo_scene_sample(state)
        append_trace(state, "prepare_scene_sample", "demo scene sample generated")
    else:
        # 真实环境里如果走到这里，通常说明 scene_id 对不上样本，
        # 或者预处理产物根本还没准备好。
        state["status"] = "FAILED"
        append_error(
            state,
            "prepare_scene_sample",
            "missing scene tensor sample",
            {"scene_sample_dir": str(SCENE_SAMPLE_DIR)},
        )
        return state

    state["scene_tensor_sample"] = sample
    # 到这里后，后面的 3D 执行节点就拿到了完整输入。
    state["status"] = "SCENE_SAMPLE_READY"
    return state
