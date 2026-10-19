"""Interpretable structure-sensitive reward for paired inference profiling."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from hydro_remote_agent.schemas.tool_spec import ToolRegistry

from .request_canonicalizer import CanonicalAgentRequest, canonicalize_agent_request


COMPONENTS = (
    "schema",
    "action",
    "intent",
    "expected_output",
    "tool_set",
    "argument_keys",
    "argument_values",
    "workflow_nodes",
    "workflow_edges",
    "artifact_references",
    "verification",
    "stop",
)


WEIGHTS_BY_ACTION = {
    "direct_answer": {
        "schema": 0.10, "action": 0.15, "intent": 0.10, "expected_output": 0.05,
        "tool_set": 0.0, "argument_keys": 0.0, "argument_values": 0.0,
        "workflow_nodes": 0.0, "workflow_edges": 0.0, "artifact_references": 0.0,
        "verification": 0.0, "stop": 0.60,
    },
    "clarification": {
        "schema": 0.10, "action": 0.15, "intent": 0.10, "expected_output": 0.05,
        "tool_set": 0.0, "argument_keys": 0.0, "argument_values": 0.0,
        "workflow_nodes": 0.0, "workflow_edges": 0.0, "artifact_references": 0.0,
        "verification": 0.0, "stop": 0.60,
    },
    "abstain": {
        "schema": 0.10, "action": 0.15, "intent": 0.10, "expected_output": 0.05,
        "tool_set": 0.0, "argument_keys": 0.0, "argument_values": 0.0,
        "workflow_nodes": 0.0, "workflow_edges": 0.0, "artifact_references": 0.0,
        "verification": 0.0, "stop": 0.60,
    },
    "tool_call": {
        "schema": 0.10, "action": 0.15, "intent": 0.10, "expected_output": 0.05,
        "tool_set": 0.15, "argument_keys": 0.10, "argument_values": 0.30,
        "workflow_nodes": 0.0, "workflow_edges": 0.0, "artifact_references": 0.0,
        "verification": 0.05, "stop": 0.0,
    },
    "workflow": {
        "schema": 0.10, "action": 0.15, "intent": 0.10, "expected_output": 0.05,
        "tool_set": 0.08, "argument_keys": 0.07, "argument_values": 0.15,
        "workflow_nodes": 0.10, "workflow_edges": 0.08, "artifact_references": 0.07,
        "verification": 0.05, "stop": 0.0,
    },
}

for _action_type, _weights in WEIGHTS_BY_ACTION.items():
    if set(_weights) != set(COMPONENTS) or not math.isclose(sum(_weights.values()), 1.0, abs_tol=1e-12):
        raise RuntimeError(f"Invalid structural reward weights for {_action_type}")


def _f1(predicted: Iterable[Any], gold: Iterable[Any]) -> float:
    predicted_set = {repr(value) for value in predicted}
    gold_set = {repr(value) for value in gold}
    if not predicted_set and not gold_set:
        return 1.0
    if not predicted_set or not gold_set:
        return 0.0
    overlap = len(predicted_set & gold_set)
    precision = overlap / len(predicted_set)
    recall = overlap / len(gold_set)
    return 2.0 * precision * recall / (precision + recall) if overlap else 0.0


def _canonical_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _argument_maps(request: CanonicalAgentRequest) -> tuple[dict[tuple[str, str], Any], set[tuple[str, str]]]:
    values: dict[tuple[str, str], Any] = {}
    keys: set[tuple[str, str]] = set()
    for owner, arguments in request.arguments:
        if not isinstance(arguments, Mapping):
            continue
        for key, value in arguments.items():
            item = (str(owner), str(key))
            keys.add(item)
            values[item] = value
    return values, keys


def _aligned_exact_score(predicted: Mapping[Any, Any], gold: Mapping[Any, Any]) -> float:
    keys = set(predicted) | set(gold)
    if not keys:
        return 1.0
    return sum(
        key in predicted and key in gold and _canonical_value(predicted[key]) == _canonical_value(gold[key])
        for key in keys
    ) / len(keys)


def _pairs_to_mapping(values: tuple[tuple[str, Any], ...]) -> dict[str, Any]:
    return {str(key): value for key, value in values}


@dataclass(frozen=True)
class StructuralRewardBreakdown:
    total: float
    schema: float
    action: float
    intent: float
    expected_output: float
    tool_set: float
    argument_keys: float
    argument_values: float
    workflow_nodes: float
    workflow_edges: float
    artifact_references: float
    verification: float
    stop: float
    invalid: bool
    candidate_error: str | None
    gold_action_type: str | None
    weights: Mapping[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StructuralContrastReward:
    """Score exact structured semantics; never use free-form string similarity."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def score(self, candidate: str | Mapping[str, Any], gold: str | Mapping[str, Any]) -> StructuralRewardBreakdown:
        canonical_gold = canonicalize_agent_request(gold, self.registry)
        if not canonical_gold.valid or canonical_gold.action_type not in WEIGHTS_BY_ACTION:
            raise ValueError(f"Gold AgentRequest is invalid: {canonical_gold.error}")
        weights = WEIGHTS_BY_ACTION[canonical_gold.action_type]
        canonical_candidate = canonicalize_agent_request(candidate, self.registry)
        if not canonical_candidate.valid:
            return StructuralRewardBreakdown(
                total=0.0,
                **{name: 0.0 for name in COMPONENTS},
                invalid=True,
                candidate_error=canonical_candidate.error,
                gold_action_type=canonical_gold.action_type,
                weights=weights,
            )

        scores = {name: 0.0 for name in COMPONENTS}
        scores["schema"] = 1.0
        same_action = canonical_candidate.action_type == canonical_gold.action_type
        scores["action"] = float(same_action)
        if same_action:
            scores["intent"] = float(canonical_candidate.intent == canonical_gold.intent)
            scores["expected_output"] = _aligned_exact_score(
                _pairs_to_mapping(canonical_candidate.expected_output),
                _pairs_to_mapping(canonical_gold.expected_output),
            )
            scores["tool_set"] = _f1(canonical_candidate.tools, canonical_gold.tools)
            predicted_values, predicted_keys = _argument_maps(canonical_candidate)
            gold_values, gold_keys = _argument_maps(canonical_gold)
            scores["argument_keys"] = _f1(predicted_keys, gold_keys)
            scores["argument_values"] = _aligned_exact_score(predicted_values, gold_values)
            scores["workflow_nodes"] = _f1(canonical_candidate.workflow_nodes, canonical_gold.workflow_nodes)
            scores["workflow_edges"] = _f1(canonical_candidate.workflow_edges, canonical_gold.workflow_edges)
            scores["artifact_references"] = _f1(canonical_candidate.artifact_references, canonical_gold.artifact_references)
            scores["verification"] = _f1(canonical_candidate.verification_policies, canonical_gold.verification_policies)
            scores["stop"] = _aligned_exact_score(
                _pairs_to_mapping(canonical_candidate.stop_fields),
                _pairs_to_mapping(canonical_gold.stop_fields),
            )
        total = sum(weights[name] * scores[name] for name in COMPONENTS)
        return StructuralRewardBreakdown(
            total=total,
            **scores,
            invalid=False,
            candidate_error=None,
            gold_action_type=canonical_gold.action_type,
            weights=weights,
        )
