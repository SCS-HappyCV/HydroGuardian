from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence

from hydro_remote_agent.schemas.tool_spec import ToolRegistry

from .request_canonicalizer import CanonicalAgentRequest, canonicalize_agent_request


DEFAULT_WEIGHTS = {
    "schema": 0.20,
    "action": 0.20,
    "tool": 0.20,
    "argument": 0.20,
    "workflow": 0.15,
    "stop": 0.05,
}


def _f1(predicted: Sequence[Any], gold: Sequence[Any]) -> float:
    predicted_set = {repr(item) for item in predicted}
    gold_set = {repr(item) for item in gold}
    if not predicted_set and not gold_set:
        return 1.0
    if not predicted_set or not gold_set:
        return 0.0
    overlap = len(predicted_set & gold_set)
    precision = overlap / len(predicted_set)
    recall = overlap / len(gold_set)
    return 2.0 * precision * recall / (precision + recall) if overlap else 0.0


def _box_iou(predicted: Sequence[float], gold: Sequence[float]) -> float:
    if len(predicted) != 4 or len(gold) != 4:
        return 0.0
    px1, py1, px2, py2 = map(float, predicted)
    gx1, gy1, gx2, gy2 = map(float, gold)
    intersection = max(0.0, min(px2, gx2) - max(px1, gx1)) * max(
        0.0, min(py2, gy2) - max(py1, gy1)
    )
    predicted_area = max(0.0, px2 - px1) * max(0.0, py2 - py1)
    gold_area = max(0.0, gx2 - gx1) * max(0.0, gy2 - gy1)
    union = predicted_area + gold_area - intersection
    return intersection / union if union > 0 else float(predicted_area == gold_area == 0)


def _value_score(path: str, predicted: Any, gold: Any) -> float:
    lower_path = path.lower()
    if isinstance(gold, Mapping):
        if not isinstance(predicted, Mapping):
            return 0.0
        keys = sorted(set(predicted) | set(gold))
        return sum(
            _value_score(f"{path}.{key}", predicted.get(key), gold.get(key))
            for key in keys
        ) / len(keys) if keys else 1.0
    if isinstance(gold, list):
        if not isinstance(predicted, list):
            return 0.0
        if any(token in lower_path for token in ("bbox", "box", "bounds", "roi")):
            try:
                return _box_iou(predicted, gold)
            except (TypeError, ValueError):
                return 0.0
        return _f1(predicted, gold)
    if isinstance(gold, (int, float)) and not isinstance(gold, bool):
        if not isinstance(predicted, (int, float)) or isinstance(predicted, bool):
            return 0.0
        if any(token in lower_path for token in ("time", "class_id", "pixels")):
            return float(predicted == gold)
        relative_error = abs(float(predicted) - float(gold)) / max(abs(float(gold)), 1e-8)
        return math.exp(-3.0 * relative_error)
    return float(predicted == gold)


def _argument_score(
    predicted: CanonicalAgentRequest,
    gold: CanonicalAgentRequest,
) -> float:
    predicted_arguments = dict(predicted.arguments)
    gold_arguments = dict(gold.arguments)
    keys = sorted(set(predicted_arguments) | set(gold_arguments))
    if not keys:
        return 1.0
    return sum(
        _value_score(key, predicted_arguments.get(key), gold_arguments.get(key))
        for key in keys
    ) / len(keys)


def _workflow_score(
    predicted: CanonicalAgentRequest,
    gold: CanonicalAgentRequest,
) -> float:
    if gold.action_type != "workflow":
        return 1.0 if predicted.action_type == gold.action_type else 0.0
    if predicted.action_type != "workflow":
        return 0.0
    node_f1 = _f1(predicted.workflow_nodes, gold.workflow_nodes)
    edge_f1 = _f1(predicted.workflow_edges, gold.workflow_edges)
    artifact_f1 = _f1(predicted.artifact_references, gold.artifact_references)
    topology_valid = float(predicted.valid)
    return 0.30 * node_f1 + 0.30 * edge_f1 + 0.20 * artifact_f1 + 0.20 * topology_valid


def _stop_score(
    predicted: CanonicalAgentRequest,
    gold: CanonicalAgentRequest,
) -> float:
    terminal_actions = {"direct_answer", "clarification", "abstain"}
    if gold.action_type not in terminal_actions:
        return float(predicted.action_type == gold.action_type)
    if predicted.action_type != gold.action_type:
        return 0.0
    return _value_score("stop", dict(predicted.stop_fields), dict(gold.stop_fields))


@dataclass(frozen=True)
class RewardBreakdown:
    total: float
    schema: float
    action: float
    tool: float
    argument: float
    workflow: float
    stop: float
    invalid: bool
    candidate_error: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GoldActionReward:
    def __init__(
        self,
        registry: ToolRegistry,
        weights: Optional[Mapping[str, float]] = None,
    ) -> None:
        self.registry = registry
        self.weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
        if set(self.weights) != set(DEFAULT_WEIGHTS):
            raise ValueError(f"Reward weights must contain {sorted(DEFAULT_WEIGHTS)}")
        if not math.isclose(sum(self.weights.values()), 1.0, abs_tol=1e-9):
            raise ValueError("Reward weights must sum to 1.0")

    def score(
        self,
        candidate: str | Mapping[str, Any],
        gold: str | Mapping[str, Any],
        *,
        allowed_actions: Optional[Sequence[str]] = None,
    ) -> RewardBreakdown:
        canonical_gold = canonicalize_agent_request(gold, self.registry)
        if not canonical_gold.valid:
            raise ValueError(f"Gold AgentRequest is invalid: {canonical_gold.error}")
        canonical_candidate = canonicalize_agent_request(candidate, self.registry)
        if not canonical_candidate.valid:
            return RewardBreakdown(
                total=0.0,
                schema=0.0,
                action=0.0,
                tool=0.0,
                argument=0.0,
                workflow=0.0,
                stop=0.0,
                invalid=True,
                candidate_error=canonical_candidate.error,
            )

        allowed = set(allowed_actions or ())
        if canonical_candidate.action_type == canonical_gold.action_type:
            action = 1.0
        elif canonical_candidate.action_type in allowed:
            action = 0.5
        else:
            action = 0.0
        same_action_type = canonical_candidate.action_type == canonical_gold.action_type
        tool = _f1(canonical_candidate.tools, canonical_gold.tools) if same_action_type else 0.0
        argument = _argument_score(canonical_candidate, canonical_gold) if same_action_type else 0.0
        workflow = _workflow_score(canonical_candidate, canonical_gold) if same_action_type else 0.0
        stop = _stop_score(canonical_candidate, canonical_gold) if same_action_type else 0.0
        components = {
            "schema": 1.0,
            "action": action,
            "tool": tool,
            "argument": argument,
            "workflow": workflow,
            "stop": stop,
        }
        total = sum(self.weights[name] * value for name, value in components.items())
        return RewardBreakdown(
            total=total,
            invalid=False,
            candidate_error=None,
            **components,
        )
