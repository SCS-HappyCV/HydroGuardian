from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from hydro_remote_agent.workflow.contracts import WorkflowResult, WorkflowStepResult


RISK_POLICY_VERSION = "hydro-risk-candidate.v1"


@dataclass(frozen=True)
class QualityGate:
    status: str
    verdict: str
    score: Optional[float]
    abstention_recommended: bool
    automation_allowed: bool
    reasons: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "verdict": self.verdict,
            "score": self.score,
            "abstention_recommended": self.abstention_recommended,
            "automation_allowed": self.automation_allowed,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class RiskCandidate:
    candidate_id: str
    rule_id: str
    source_step_id: str
    source_tool: str
    risk_type: str
    title: str
    risk_level: str
    score: float
    score_kind: str
    summary: str
    review_required: bool
    recommendation: str
    evidence_refs: Tuple[str, ...]
    region_scope: Dict[str, Any]
    signals: Dict[str, Any]
    quality_gate: QualityGate

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": RISK_POLICY_VERSION,
            "candidate_id": self.candidate_id,
            "rule_id": self.rule_id,
            "source_step_id": self.source_step_id,
            "source_tool": self.source_tool,
            "risk_type": self.risk_type,
            "title": self.title,
            "risk_level": self.risk_level,
            "score": self.score,
            "score_kind": self.score_kind,
            "summary": self.summary,
            "review_required": self.review_required,
            "requires_business_confirmation": True,
            "recommendation": self.recommendation,
            "evidence_refs": list(self.evidence_refs),
            "region_scope": dict(self.region_scope),
            "signals": dict(self.signals),
            "quality_gate": self.quality_gate.to_dict(),
        }


def _number(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _quality_gate(step: WorkflowStepResult) -> QualityGate:
    verification = step.verification_result
    if verification is None or verification.status != "succeeded":
        return QualityGate(
            status="review_required",
            verdict="unavailable",
            score=None,
            abstention_recommended=False,
            automation_allowed=False,
            reasons=("quality_verification_unavailable",),
        )
    metrics = verification.metrics
    verdict = str(metrics.get("verdict", "unavailable"))
    score = _number(metrics.get("quality_score"))
    abstention = bool(metrics.get("abstention_recommended", False))
    reasons = []
    if verdict != "passed":
        reasons.append(f"quality_verdict_{verdict}")
    if score is None or score < 0.8:
        reasons.append("quality_score_below_gate")
    if abstention:
        reasons.append("quality_abstention_recommended")
    allowed = not reasons
    return QualityGate(
        status="passed" if allowed else "review_required",
        verdict=verdict,
        score=score,
        abstention_recommended=abstention,
        automation_allowed=allowed,
        reasons=tuple(reasons),
    )


def _evidence_refs(step: WorkflowStepResult) -> Tuple[str, ...]:
    values: Iterable[Any] = ()
    if step.result is not None:
        values = step.result.artifacts.values()
    quality_values: Iterable[Any] = ()
    if step.verification_result is not None:
        quality_values = step.verification_result.artifacts.values()
    return tuple(
        dict.fromkeys(
            value
            for value in (*values, *quality_values)
            if isinstance(value, str) and value
        )
    )


def _gated_level(base_level: str, gate: QualityGate) -> str:
    return base_level if gate.automation_allowed else "review_required"


def _change_candidate(execution_id: str, step: WorkflowStepResult) -> Optional[RiskCandidate]:
    if step.result is None:
        return None
    metrics = step.result.metrics
    changed_pixels = int(_number(metrics.get("changed_pixels")) or 0)
    changed_ratio = _number(metrics.get("changed_ratio")) or 0.0
    region_count = int(_number(metrics.get("region_count")) or 0)
    if changed_pixels <= 0 or region_count <= 0:
        return None
    gate = _quality_gate(step)
    extent_score = min(changed_ratio / 0.02, 1.0) * 20.0
    region_score = min(region_count / 5.0, 1.0) * 15.0
    evidence_score = round(min(85.0, 50.0 + extent_score + region_score), 1)
    base_level = "medium" if changed_ratio >= 0.02 or region_count >= 5 else "low"
    return RiskCandidate(
        candidate_id=f"{execution_id}-{step.step_id}-change",
        rule_id="change-region-present-v1",
        source_step_id=step.step_id,
        source_tool=step.tool,
        risk_type="change_anomaly_candidate",
        title="遥感变化异常候选",
        risk_level=_gated_level(base_level, gate),
        score=evidence_score,
        score_kind="evidence_strength",
        summary=(
            f"变化检测发现 {region_count} 个候选区域，共 {changed_pixels} 个变化像素，"
            f"占影像面积 {changed_ratio:.4%}。变化性质仍需结合巡查规则与现场证据确认。"
        ),
        review_required=True,
        recommendation="核对前后时相影像和变化区域，确认是否属于工程扰动、设施变化或自然变化。",
        evidence_refs=_evidence_refs(step),
        region_scope={"kind": "artifact_regions", "artifact_role": "change_regions"},
        signals={
            "changed_pixels": changed_pixels,
            "changed_ratio": changed_ratio,
            "region_count": region_count,
        },
        quality_gate=gate,
    )


def _geometry_candidate(execution_id: str, step: WorkflowStepResult) -> Optional[RiskCandidate]:
    if step.result is None:
        return None
    arguments: Mapping[str, Any] = step.result.arguments
    metrics = step.result.metrics
    operation = str(arguments.get("operation", ""))
    outcome = str(metrics.get("outcome", ""))
    selected_points = int(_number(metrics.get("selected_points")) or 0)
    selected_ratio = _number(metrics.get("selected_target_ratio")) or 0.0
    if operation not in {"near", "above"} or outcome != "result" or selected_points <= 0:
        return None
    gate = _quality_gate(step)
    evidence_score = round(min(85.0, 55.0 + min(selected_ratio, 1.0) * 30.0), 1)
    relation_label = "邻近关系" if operation == "near" else "高程关系"
    risk_type = "proximity_relation_candidate" if operation == "near" else "elevation_relation_candidate"
    return RiskCandidate(
        candidate_id=f"{execution_id}-{step.step_id}-{operation}",
        rule_id=f"geometry-{operation}-match-v1",
        source_step_id=step.step_id,
        source_tool=step.tool,
        risk_type=risk_type,
        title=f"{relation_label}异常候选",
        risk_level=_gated_level("low", gate),
        score=evidence_score,
        score_kind="evidence_strength",
        summary=(
            f"空间分析命中 {selected_points} 个目标点，占目标类别 {selected_ratio:.2%}。"
            "该结果仅说明几何关系成立，是否构成业务风险仍需匹配正式巡查规则。"
        ),
        review_required=True,
        recommendation="核对目标与参照类别、空间阈值及现场场景，确认该几何关系是否违反业务规则。",
        evidence_refs=_evidence_refs(step),
        region_scope={"kind": "point_mask", "artifact_role": "relation_mask"},
        signals={
            "operation": operation,
            "target_class_id": arguments.get("target_class_id"),
            "reference_class_id": arguments.get("reference_class_id"),
            "selected_points": selected_points,
            "selected_target_ratio": selected_ratio,
        },
        quality_gate=gate,
    )


def compile_risk_candidates(workflow: WorkflowResult) -> Tuple[RiskCandidate, ...]:
    if workflow.status != "succeeded":
        return ()
    candidates = []
    for step in workflow.steps:
        if step.status != "succeeded":
            continue
        candidate = None
        if step.tool == "image_change_detection":
            candidate = _change_candidate(workflow.execution_id, step)
        elif step.tool == "geometry_relation_analysis":
            candidate = _geometry_candidate(workflow.execution_id, step)
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)
