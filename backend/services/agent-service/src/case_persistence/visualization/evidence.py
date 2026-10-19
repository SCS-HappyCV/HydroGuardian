# EvidencePack 可视化摘要构建工具。
# 本模块把证据指标、风险框和点云分段统一整理成前端风险工作台可消费的轻量结构。
from __future__ import annotations

from typing import Any, Dict

from .projection import build_region_bbox_3d, project_region_to_image


RISK_LEVEL_COLORS = {
    "HIGH": "#ef4444",
    "MEDIUM": "#f59e0b",
    "LOW": "#22c55e",
    "REVIEW_REQUIRED": "#06b6d4",
    "EVIDENCE_ONLY": "#64748b",
}


# 构建 EvidencePack 指标面板数据，避免前端直接理解完整证据对象。
def build_evidence_metrics(evidence_pack: Dict[str, Any]) -> Dict[str, Any]:
    candidate_regions = _candidate_regions(evidence_pack)
    return {
        "schema_version": "evidence_metrics.v1",
        "status": evidence_pack.get("status", ""),
        "target_hit": bool(evidence_pack.get("target_hit", False)),
        "decision_kind": evidence_pack.get("decision_kind", ""),
        "review_required": bool(evidence_pack.get("review_required", False)),
        "confidence": _float_value(evidence_pack.get("confidence")),
        "confidence_components": _dict_value(evidence_pack.get("confidence_components")),
        "selected_candidate_idx": evidence_pack.get("selected_candidate_idx"),
        "selected_candidate_score": _float_value(evidence_pack.get("selected_candidate_score")),
        "selected_candidate_posterior": _float_value(evidence_pack.get("selected_candidate_posterior")),
        "selected_candidate_is_no_target": bool(evidence_pack.get("selected_candidate_is_no_target", False)),
        "selected_verifier_score": _float_value(evidence_pack.get("selected_verifier_score")),
        "posterior_no_target_mass": _float_value(evidence_pack.get("posterior_no_target_mass")),
        "abstain_probability": _float_value(evidence_pack.get("abstain_probability")),
        "selected_mask_mass": _float_value(evidence_pack.get("selected_mask_mass")),
        "selected_mask_peak": _float_value(evidence_pack.get("selected_mask_peak")),
        "mask_selection_mode": evidence_pack.get("mask_selection_mode", ""),
        "candidate_region_count": len(candidate_regions),
        "evidence_summary": _string_list(evidence_pack.get("evidence_summary")),
    }


# 构建正射图上的风险叠加框；每个候选区域都会得到一个可点击 overlay。
def build_risk_overlays(
    evidence_pack: Dict[str, Any],
    risk_cards: list[Dict[str, Any]],
    ortho_asset: Dict[str, Any],
) -> list[Dict[str, Any]]:
    display_width = int(ortho_asset.get("display_width") or 0)
    display_height = int(ortho_asset.get("display_height") or 0)
    risk_by_region = _risk_cards_by_region(risk_cards)

    overlays: list[Dict[str, Any]] = []
    for index, region in enumerate(_candidate_regions(evidence_pack), start=1):
        region_id = str(region.get("region_id") or f"region_{index}")
        risk_card = risk_by_region.get(region_id, {})
        risk_level = _risk_level(risk_card)
        projection = project_region_to_image(region, display_width, display_height)
        overlay = {
            "overlay_id": f"overlay_{region_id}",
            "region_id": region_id,
            "label": f"候选风险区域 {index}",
            "risk_card_id": risk_card.get("risk_card_id", ""),
            "risk_type": risk_card.get("risk_type", ""),
            "risk_level": risk_level,
            "risk_score": _float_value(risk_card.get("risk_score"), _float_value(region.get("score"))),
            "review_required": bool(risk_card.get("review_required", evidence_pack.get("review_required", False))),
            "candidate_score": _float_value(region.get("score")),
            "support": _float_value(region.get("support")),
            "point_count": int(region.get("point_count") or 0),
            "bbox_3d": build_region_bbox_3d(region),
            "centroid": _float_list(region.get("centroid")),
            "summary": region.get("summary", ""),
            "color": RISK_LEVEL_COLORS.get(risk_level, RISK_LEVEL_COLORS["EVIDENCE_ONLY"]),
        }
        # 投影失败时仍保留区域指标，前端可以在列表里展示。
        overlay.update(projection)
        overlays.append(overlay)
    return overlays


# 构建 Three.js 点云分段信息；前端用 point_indices 高亮 EvidencePack 候选区域。
def build_point_cloud_segments(
    evidence_pack: Dict[str, Any],
    risk_cards: list[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    risk_by_region = _risk_cards_by_region(risk_cards)
    segments: list[Dict[str, Any]] = []

    for index, region in enumerate(_candidate_regions(evidence_pack), start=1):
        region_id = str(region.get("region_id") or f"region_{index}")
        risk_card = risk_by_region.get(region_id, {})
        risk_level = _risk_level(risk_card)
        segments.append(
            {
                "segment_id": f"segment_{region_id}",
                "region_id": region_id,
                "label": f"候选风险区域 {index}",
                "risk_card_id": risk_card.get("risk_card_id", ""),
                "risk_level": risk_level,
                "risk_score": _float_value(risk_card.get("risk_score"), _float_value(region.get("score"))),
                "score": _float_value(region.get("score")),
                "support": _float_value(region.get("support")),
                "point_count": int(region.get("point_count") or 0),
                "bbox_3d": build_region_bbox_3d(region),
                "point_indices": _int_list(region.get("point_indices")),
                "color": RISK_LEVEL_COLORS.get(risk_level, RISK_LEVEL_COLORS["EVIDENCE_ONLY"]),
                "summary": region.get("summary", ""),
            }
        )
    return segments


# 返回风险卡中绑定的首个候选区域 id，用于 Three.js 默认选中。
def selected_region_id(risk_cards: list[Dict[str, Any]]) -> str:
    for card in risk_cards:
        region_id = card.get("candidate_region_id")
        if region_id:
            return str(region_id)
    return ""


# 从 EvidencePack 中安全提取候选区域列表。
def _candidate_regions(evidence_pack: Dict[str, Any]) -> list[Dict[str, Any]]:
    regions = evidence_pack.get("candidate_regions")
    if not isinstance(regions, list):
        return []
    return [region for region in regions if isinstance(region, dict)]


# 按 candidate_region_id 建立风险卡索引，便于 overlay 和 segment 对齐。
def _risk_cards_by_region(risk_cards: list[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for card in risk_cards:
        if not isinstance(card, dict):
            continue
        region_id = card.get("candidate_region_id")
        if region_id:
            result[str(region_id)] = card
    return result


# 归一化风险等级；没有风险卡的候选区域按证据层展示。
def _risk_level(risk_card: Dict[str, Any]) -> str:
    raw_level = str(risk_card.get("risk_level") or "").upper()
    return raw_level if raw_level else "EVIDENCE_ONLY"


# 安全读取 dict 字段。
def _dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


# 安全读取 float 字段。
def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return default


# 安全读取 float 列表字段。
def _float_list(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    result: list[float] = []
    for item in value:
        try:
            result.append(round(float(item), 6))
        except (TypeError, ValueError):
            return []
    return result


# 安全读取 int 列表字段，保留 EvidenceCompiler 已经截断过的点索引。
def _int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


# 安全读取字符串列表字段。
def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
