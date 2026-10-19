# agent 执行结果快照构建器。
# 快照用于 case 持久化、接口诊断和后续证据链回放；本模块避免把大张量直接写进去。

from __future__ import annotations

from typing import Any, Dict

from .visualization import build_visualization_snapshot
from scene_samples import summarize_scene_sample
from state import AgentState


# 安全截断列表，防止 trace/errors 或卡片集合过大。
def _limited_list(value: Any, limit: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:limit]


# 提取原始 3D 执行输出摘要，不把模型大输出整体塞进 case。
def _summarize_raw_executor_output(raw_output: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw_output, dict) or not raw_output:
        return {}

    execution_result = raw_output.get("execution_result")
    if not isinstance(execution_result, dict):
        execution_result = {}
    outputs = execution_result.get("outputs")
    if not isinstance(outputs, dict):
        outputs = {}

    return {
        "ok": raw_output.get("ok"),
        "message": raw_output.get("message"),
        "checkpoint_name": raw_output.get("checkpoint_name"),
        "checkpoint_path": raw_output.get("checkpoint_path"),
        "model_config": execution_result.get("model_config", {}),
        "output_keys": sorted(outputs.keys()),
    }


# 从 scene_tensor_sample 中生成可持久化摘要，避免保存图像/点云大数组。
def _sample_summary(state: AgentState) -> Dict[str, Any]:
    sample = state.get("scene_tensor_sample") or {}
    if not isinstance(sample, dict) or not sample:
        return {}
    return summarize_scene_sample(sample, source="agent_state")


# 构建完整 agent_result 快照，供 case_agent_result 表持久化和调试返回使用。
def build_agent_result_snapshot(state: AgentState) -> Dict[str, Any]:
    evidence_pack = state.get("evidence_pack") or {}
    if not isinstance(evidence_pack, dict):
        evidence_pack = {}

    return {
        "schema_version": "agent_result_snapshot.v1",
        "case_id": state.get("case_id", ""),
        "task_id": state.get("task_id", ""),
        "task_text": state.get("task_text", ""),
        "scene_id": state.get("scene_id", ""),
        "sample_id": state.get("sample_id", ""),
        "status": state.get("status", ""),
        "task_intent": state.get("task_intent") or {},
        "program_bundle": state.get("program_bundle") or {},
        "selected_program": state.get("selected_program") or {},
        "scene_sample_summary": _sample_summary(state),
        "raw_executor_summary": _summarize_raw_executor_output(state.get("raw_executor_output") or {}),
        "evidence_pack": evidence_pack,
        "change_pack": state.get("change_pack") or {},
        "visualization": build_visualization_snapshot(state),
        "risk_cards": state.get("risk_cards") or [],
        "recommendation_cards": state.get("recommendation_cards") or [],
        "work_orders": state.get("work_orders") or [],
        "trace": _limited_list(state.get("trace"), 80),
        "errors": _limited_list(state.get("errors"), 40),
    }
