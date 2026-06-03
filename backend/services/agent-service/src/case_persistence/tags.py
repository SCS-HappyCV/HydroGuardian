# case-service tags 字段摘要载荷。
# 完整 agent 结果已保存到 case_agent_result 表；tags 只保留检索和展示用的轻量索引信息。

from __future__ import annotations

import json
from typing import Any, Dict


# 构建可塞进 CreateCaseRequest.tags 的紧凑载荷。
def build_case_tags_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    evidence_pack = snapshot.get("evidence_pack")
    if not isinstance(evidence_pack, dict):
        evidence_pack = {}
    risk_cards = snapshot.get("risk_cards") if isinstance(snapshot.get("risk_cards"), list) else []
    primary_risk = risk_cards[0] if risk_cards and isinstance(risk_cards[0], dict) else {}
    sample_summary = snapshot.get("scene_sample_summary")
    if not isinstance(sample_summary, dict):
        sample_summary = {}

    return {
        "tags": ["langgraph", "hydro-program3d", "agent-service"],
        "schemaVersion": "case_tags.agent_snapshot.v1",
        "riskType": primary_risk.get("risk_type"),
        "riskScore": primary_risk.get("risk_score"),
        "reviewRequired": primary_risk.get("review_required"),
        "evidenceStatus": evidence_pack.get("status"),
        "parserSource": (snapshot.get("task_intent") or {}).get("parser_source"),
        "executionStatus": snapshot.get("status"),
        "sampleSummary": sample_summary,
        "agentResultStorage": "case_agent_result",
        "agentResultSnapshotSchema": snapshot.get("schema_version"),
    }


# 尝试解析 case-service 返回的 tags，解析失败时保留原始字符串。
def parse_case_tags(raw_tags: str) -> Dict[str, Any]:
    if not raw_tags:
        return {}
    try:
        payload = json.loads(raw_tags)
    except json.JSONDecodeError:
        return {"raw": raw_tags}
    return payload if isinstance(payload, dict) else {"raw": raw_tags}
