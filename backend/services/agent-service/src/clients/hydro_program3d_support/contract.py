# hydro-program3d 请求摘要和 EvidencePack 契约校验。
# 本模块只处理协议形状，不做 HTTP 调用。

from __future__ import annotations

from typing import Any, Dict

from .errors import HydroProgram3DError


# 风险层消费 EvidencePack 时至少需要这些字段存在。
REQUIRED_EVIDENCE_FIELDS = [
    "status",
    "target_hit",
    "review_required",
    "confidence",
    "candidate_regions",
    "evidence_summary",
]


# 从执行请求中提取轻量摘要，避免把大张量写进错误和 trace。
def summarize_execute_request(body: Dict[str, Any]) -> Dict[str, Any]:
    sample = body.get("sample") if isinstance(body.get("sample"), dict) else {}
    program = body.get("program") if isinstance(body.get("program"), dict) else {}
    bundle = body.get("program_bundle") if isinstance(body.get("program_bundle"), dict) else {}

    return {
        "checkpoint_name": body.get("checkpoint_name", ""),
        "device": body.get("device", ""),
        "sample_id": sample.get("sample_id", ""),
        "sample_text": sample.get("text", ""),
        "target": program.get("target", ""),
        "target_label_ids": program.get("target_label_ids", []),
        "relation_count": len(program.get("relations", []) or []),
        "negative_label_ids": program.get("negative_label_ids", []),
        "program_bundle_candidates": len(bundle.get("candidates", []) or []),
    }


# 构建 /compile_evidence 请求，保证主 client 里不重复拼字段。
def build_compile_request(state_sample: Dict[str, Any], execute_payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sample": state_sample,
        "execution_result": execute_payload,
        "batch_index": 0,
    }


# 校验 /compile_evidence 返回的 EvidencePack 是否满足风险层最小契约。
def validate_evidence_pack(evidence_pack: Any) -> Dict[str, Any]:
    if not isinstance(evidence_pack, dict):
        raise HydroProgram3DError(
            stage="compile_evidence",
            error_type="invalid_evidence_pack",
            message="/compile_evidence returned non-object evidence_pack",
            retryable=False,
        )

    missing = [field for field in REQUIRED_EVIDENCE_FIELDS if field not in evidence_pack]
    if missing:
        raise HydroProgram3DError(
            stage="compile_evidence",
            error_type="invalid_evidence_pack",
            message=f"evidence_pack missing required fields: {', '.join(missing)}",
            retryable=False,
        )

    if not isinstance(evidence_pack.get("candidate_regions"), list):
        raise HydroProgram3DError(
            stage="compile_evidence",
            error_type="invalid_evidence_pack",
            message="evidence_pack.candidate_regions must be a list",
            retryable=False,
        )
    if not isinstance(evidence_pack.get("evidence_summary"), list):
        raise HydroProgram3DError(
            stage="compile_evidence",
            error_type="invalid_evidence_pack",
            message="evidence_pack.evidence_summary must be a list",
            retryable=False,
        )
    return evidence_pack
