from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from hydro_remote_agent.tool_aliases import execution_request_with_aliases


CAPABILITY_POLICY_SCHEMA_VERSION = "cmge.capability_policy.v1"


@dataclass(frozen=True)
class CapabilityRule:
    rule_id: str
    source_tool: str
    target_tool: str
    intents: tuple[str, ...]
    enabled: bool
    evidence: Mapping[str, Any]


@dataclass(frozen=True)
class CapabilityPolicy:
    policy_id: str
    rules: tuple[CapabilityRule, ...]


def load_capability_policy(path: str | Path, registry) -> CapabilityPolicy:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, Mapping):
        raise ValueError("Capability policy must contain an object")
    if payload.get("schema_version") != CAPABILITY_POLICY_SCHEMA_VERSION:
        raise ValueError(f"Capability policy requires {CAPABILITY_POLICY_SCHEMA_VERSION}")
    policy_id = str(payload.get("policy_id", "")).strip()
    if not policy_id:
        raise ValueError("Capability policy requires policy_id")
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError("Capability policy requires at least one rule")
    rules = []
    seen_ids = set()
    for raw in raw_rules:
        if not isinstance(raw, Mapping):
            raise ValueError("Capability policy rules must be objects")
        rule_id = str(raw.get("rule_id", "")).strip()
        if not rule_id or rule_id in seen_ids:
            raise ValueError(f"Invalid or duplicate capability rule_id {rule_id!r}")
        seen_ids.add(rule_id)
        source = str(raw.get("source_tool", "")).strip()
        target = str(raw.get("target_tool", "")).strip()
        registry.get(source)
        registry.get(target)
        raw_intents = raw.get("intents", [])
        if not isinstance(raw_intents, list) or not all(
            isinstance(value, str) and value.strip() for value in raw_intents
        ):
            raise ValueError(f"Rule {rule_id!r} intents must be non-empty strings")
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"Rule {rule_id!r} enabled must be boolean")
        evidence = raw.get("evidence", {})
        if not isinstance(evidence, Mapping):
            raise ValueError(f"Rule {rule_id!r} evidence must be an object")
        rules.append(
            CapabilityRule(
                rule_id=rule_id,
                source_tool=source,
                target_tool=target,
                intents=tuple(str(value) for value in raw_intents),
                enabled=enabled,
                evidence=dict(evidence),
            )
        )
    return CapabilityPolicy(policy_id=policy_id, rules=tuple(rules))


def apply_capability_policy(
    request: Mapping[str, Any],
    policy: CapabilityPolicy,
    registry,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rewritten = copy.deepcopy(dict(request))
    intent = str(rewritten.get("intent", ""))
    decisions = []
    for rule in policy.rules:
        if not rule.enabled or (rule.intents and intent not in rule.intents):
            continue
        candidate = execution_request_with_aliases(
            rewritten,
            {rule.source_tool: rule.target_tool},
            registry,
        )
        if candidate == rewritten:
            continue
        rewritten = candidate
        decisions.append(
            {
                "rule_id": rule.rule_id,
                "intent": intent,
                "source_tool": rule.source_tool,
                "target_tool": rule.target_tool,
            }
        )
    return rewritten, decisions
