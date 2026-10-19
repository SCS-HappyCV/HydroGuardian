# agent_result 可视化视图模型总装配器。
# 本模块把场景资产、EvidencePack、RiskCard 和 ChangePack 汇总成风险工作台的一站式轻量数据。
from __future__ import annotations

from typing import Any, Dict

from state import AgentState

from .assets import (
    as_dict,
    build_change_comparison_asset,
    build_ortho_asset,
    build_point_cloud_asset,
    sample_metadata,
    sample_source_files,
)
from .evidence import (
    build_evidence_metrics,
    build_point_cloud_segments,
    build_risk_overlays,
    selected_region_id,
)


# 构建完整可视化快照；该快照只保存轻量元数据和 fileId/downloadUrl 引用。
def build_visualization_snapshot(state: AgentState) -> Dict[str, Any]:
    sample = as_dict(state.get("scene_tensor_sample"))
    evidence_pack = as_dict(state.get("evidence_pack"))
    change_pack = as_dict(state.get("change_pack"))
    risk_cards = _dict_list(state.get("risk_cards"))

    ortho = build_ortho_asset(sample)
    point_cloud = build_point_cloud_asset(sample)
    point_cloud["segments"] = build_point_cloud_segments(evidence_pack, risk_cards)
    point_cloud["selected_region_id"] = selected_region_id(risk_cards)

    return {
        "schema_version": "agent_visualization.v1",
        "available": bool(sample or evidence_pack or risk_cards),
        "scene_id": state.get("scene_id", ""),
        "sample_id": state.get("sample_id", "") or sample.get("sample_id", ""),
        "asset_roles": sorted(sample_source_files(sample).keys()),
        "ortho": ortho,
        "risk_overlays": build_risk_overlays(evidence_pack, risk_cards, ortho),
        "evidence_metrics": build_evidence_metrics(evidence_pack),
        "change_comparison": build_change_comparison_asset(sample, change_pack),
        "point_cloud": point_cloud,
        "scene_quality": _scene_quality(sample),
    }


# 只保留列表中的 dict 项，避免上游异常数据影响快照序列化。
def _dict_list(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


# 提取场景预处理质量报告；它体量小，适合放进风险工作台辅助说明。
def _scene_quality(sample: Dict[str, Any]) -> Dict[str, Any]:
    metadata = sample_metadata(sample)
    quality_report = metadata.get("quality_report")
    return quality_report if isinstance(quality_report, dict) else {}
