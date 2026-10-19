"""Graph-canonical Structural Reward B with workflow alpha-renaming invariance."""
from __future__ import annotations

import copy
import itertools
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from hydro_remote_agent.schemas.tool_spec import ToolRegistry

from .request_canonicalizer import CanonicalAgentRequest, canonicalize_agent_request
from .structural_contrast_reward import StructuralContrastReward, StructuralRewardBreakdown


ARTIFACT_REF = re.compile(
    r"^\$\{(?P<step>[A-Za-z][A-Za-z0-9_-]*)\.artifacts\.(?P<artifact>[A-Za-z][A-Za-z0-9_]*)\}$"
)
MAX_WORKFLOW_NODES = 8
MAX_TOPOLOGICAL_ORDERS = 100_000
REFERENCE_FIELDS = {
    "depends_on", "source_step_id", "target_step_id", "producer_step_id",
    "consumer_step_id", "verification_owner", "verification_target",
    "verification_target_step_id", "stop_step_id", "stop_target_step_id",
}


@dataclass(frozen=True)
class CanonicalizationInfo:
    status: str
    nodes: int
    topological_orders_considered: int
    canonical_ties: int
    ambiguity_resolution: str
    error: str | None = None
    original_to_canonical: tuple[tuple[str, str], ...] = ()


def _payload(value: str | Mapping[str, Any]) -> Any:
    parsed = json.loads(value) if isinstance(value, str) else value
    return copy.deepcopy(parsed)


def _is_reference_field(field_name: str | None) -> bool:
    return bool(
        field_name in REFERENCE_FIELDS
        or (field_name and (field_name.endswith("_step_id") or field_name.endswith("_step_ids")))
    )


def rewrite_step_references(value: Any, rename: Mapping[str, str], field_name: str | None = None) -> Any:
    """Rewrite exact structured references, never free-form string similarity."""
    if isinstance(value, str):
        match = ARTIFACT_REF.fullmatch(value)
        if match and match.group("step") in rename:
            return f"${{{rename[match.group('step')]}.artifacts.{match.group('artifact')}}}"
        if _is_reference_field(field_name) and value in rename:
            return rename[value]
        return value
    if isinstance(value, list):
        rewritten = [rewrite_step_references(item, rename, field_name) for item in value]
        return sorted(rewritten) if field_name == "depends_on" else rewritten
    if isinstance(value, dict):
        return {key: rewrite_step_references(child, rename, str(key)) for key, child in value.items()}
    return value


def _topological_orders(ids: tuple[str, ...], dependencies: Mapping[str, frozenset[str]]) -> tuple[list[tuple[str, ...]], bool]:
    orders: list[tuple[str, ...]] = []
    exceeded = False

    def visit(prefix: tuple[str, ...], remaining: frozenset[str]) -> None:
        nonlocal exceeded
        if exceeded:
            return
        if not remaining:
            orders.append(prefix)
            if len(orders) > MAX_TOPOLOGICAL_ORDERS:
                exceeded = True
            return
        placed = set(prefix)
        available = sorted(node for node in remaining if dependencies[node] <= placed)
        if not available:
            return
        for node in available:
            visit(prefix + (node,), remaining - {node})

    visit((), frozenset(ids))
    return orders, exceeded


def _anonymize_references(value: Any, field_name: str | None = None) -> Any:
    if isinstance(value, str):
        match = ARTIFACT_REF.fullmatch(value)
        if match:
            return f"${{@producer.artifacts.{match.group('artifact')}}}"
        if _is_reference_field(field_name):
            return "@step"
        return value
    if isinstance(value, list):
        return [_anonymize_references(item, field_name) for item in value]
    if isinstance(value, dict):
        return {key: _anonymize_references(child, str(key)) for key, child in value.items()}
    return value


def _intrinsic_semantic_key(step: Mapping[str, Any]) -> str:
    semantic = {
        "tool": step.get("tool"),
        "verification": step.get("verification", "auto"),
        "arguments": _anonymize_references(step.get("arguments", {})),
        "other": {
            key: _anonymize_references(value, str(key))
            for key, value in step.items()
            if key not in {"step_id", "depends_on", "tool", "verification", "arguments"}
        },
    }
    return json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _candidate_mappings(ids: tuple[str, ...], by_id: Mapping[str, Mapping[str, Any]]) -> tuple[list[dict[str, str]], bool]:
    groups: dict[str, list[str]] = {}
    for step_id in ids:
        groups.setdefault(_intrinsic_semantic_key(by_id[step_id]), []).append(step_id)
    ordered_groups = [tuple(sorted(groups[key])) for key in sorted(groups)]
    mappings: list[dict[str, str]] = []
    exceeded = False

    def visit(group_index: int, next_id: int, mapping: dict[str, str]) -> None:
        nonlocal exceeded
        if exceeded:
            return
        if group_index == len(ordered_groups):
            mappings.append(dict(mapping))
            if len(mappings) > MAX_TOPOLOGICAL_ORDERS:
                exceeded = True
            return
        group = ordered_groups[group_index]
        for permutation in itertools.permutations(group):
            for offset, step_id in enumerate(permutation):
                mapping[step_id] = f"step_{next_id + offset}"
            visit(group_index + 1, next_id + len(group), mapping)
            for step_id in group:
                mapping.pop(step_id, None)

    visit(0, 0, {})
    return mappings, exceeded


def _canonical_topological_order(
    ids: tuple[str, ...], dependencies: Mapping[str, frozenset[str]], rename: Mapping[str, str]
) -> tuple[str, ...]:
    order: list[str] = []
    remaining = set(ids)
    while remaining:
        placed = set(order)
        available = [node for node in remaining if dependencies[node] <= placed]
        if not available:
            return ()
        node = min(available, key=lambda item: rename[item])
        order.append(node)
        remaining.remove(node)
    return tuple(order)


def _fail_closed(payload: dict[str, Any], reason: str, nodes: int) -> tuple[dict[str, Any], CanonicalizationInfo]:
    failed = copy.deepcopy(payload)
    failed["schema_version"] = f"canonicalization_error:{reason}"
    return failed, CanonicalizationInfo("invalid", nodes, 0, 0, "fail_closed", reason)


def canonicalize_workflow_graph(value: str | Mapping[str, Any]) -> tuple[Any, CanonicalizationInfo]:
    payload = _payload(value)
    if not isinstance(payload, dict):
        return payload, CanonicalizationInfo("noop", 0, 0, 0, "not_an_object")
    action = payload.get("action")
    if not isinstance(action, dict) or action.get("type") != "workflow":
        return payload, CanonicalizationInfo("noop", 0, 0, 0, "non_workflow")
    steps = action.get("steps")
    if not isinstance(steps, list) or not steps or not all(isinstance(step, dict) for step in steps):
        return payload, CanonicalizationInfo("invalid", 0, 0, 0, "fail_closed", "malformed_steps")
    ids = tuple(str(step.get("step_id", "")) for step in steps)
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        return payload, CanonicalizationInfo("invalid", len(ids), 0, 0, "fail_closed", "missing_or_duplicate_step_id")
    if len(ids) > MAX_WORKFLOW_NODES:
        return _fail_closed(payload, "node_budget_exceeded", len(ids))

    known = set(ids)
    dependencies: dict[str, frozenset[str]] = {}
    previous: set[str] = set()
    for step_id, step in zip(ids, steps):
        raw_dependencies = step.get("depends_on", [])
        if not isinstance(raw_dependencies, list) or not all(isinstance(item, str) for item in raw_dependencies):
            return payload, CanonicalizationInfo("invalid", len(ids), 0, 0, "fail_closed", "malformed_dependencies")
        dependency_set = frozenset(raw_dependencies)
        if not dependency_set <= known:
            return payload, CanonicalizationInfo("invalid", len(ids), 0, 0, "fail_closed", "undefined_dependency")
        if not dependency_set <= previous:
            return payload, CanonicalizationInfo("invalid", len(ids), 0, 0, "fail_closed", "non_topological_or_cycle")
        dependencies[step_id] = dependency_set
        previous.add(step_id)

    orders, exceeded = _topological_orders(ids, dependencies)
    if exceeded:
        return _fail_closed(payload, "topological_order_budget_exceeded", len(ids))
    if not orders:
        return payload, CanonicalizationInfo("invalid", len(ids), 0, 0, "fail_closed", "cycle")

    by_id = {step_id: step for step_id, step in zip(ids, steps)}
    mappings, mapping_exceeded = _candidate_mappings(ids, by_id)
    if mapping_exceeded:
        return _fail_closed(payload, "semantic_tie_mapping_budget_exceeded", len(ids))
    best_encoding: str | None = None
    best_payload: dict[str, Any] | None = None
    best_mapping: dict[str, str] | None = None
    ties = 0
    for rename in mappings:
        order = _canonical_topological_order(ids, dependencies, rename)
        if not order:
            continue
        normalized = rewrite_step_references(payload, rename)
        normalized_steps = []
        for step_id in order:
            step = rewrite_step_references(by_id[step_id], rename)
            step["step_id"] = rename[step_id]
            step["depends_on"] = sorted(rename[item] for item in dependencies[step_id])
            normalized_steps.append(step)
        normalized["action"]["steps"] = normalized_steps
        encoding = json.dumps(normalized_steps, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if best_encoding is None or encoding < best_encoding:
            best_encoding, best_payload, best_mapping, ties = encoding, normalized, dict(rename), 1
        elif encoding == best_encoding:
            ties += 1
    assert best_payload is not None and best_mapping is not None
    return best_payload, CanonicalizationInfo(
        "canonicalized", len(ids), len(orders), ties,
        "intrinsic_semantic_labels_then_lexicographic_graph_disambiguation",
        original_to_canonical=tuple(sorted(best_mapping.items())),
    )


def normalize_workflow_step_ids(value: str | Mapping[str, Any]) -> Any:
    return canonicalize_workflow_graph(value)[0]


def _graph_parts(payload: Mapping[str, Any]) -> tuple[tuple[str, ...], dict[str, frozenset[str]], dict[str, Mapping[str, Any]]]:
    steps = payload["action"]["steps"]
    ids = tuple(str(step["step_id"]) for step in steps)
    dependencies = {str(step["step_id"]): frozenset(str(item) for item in step.get("depends_on", [])) for step in steps}
    return ids, dependencies, {str(step["step_id"]): step for step in steps}


def _normalize_with_mapping(
    payload: Mapping[str, Any], ids: tuple[str, ...], dependencies: Mapping[str, frozenset[str]],
    by_id: Mapping[str, Mapping[str, Any]], rename: Mapping[str, str],
) -> dict[str, Any]:
    normalized = rewrite_step_references(payload, rename)
    order = _canonical_topological_order(ids, dependencies, rename)
    normalized_steps = []
    for step_id in order:
        step = rewrite_step_references(by_id[step_id], rename)
        step["step_id"] = rename[step_id]
        step["depends_on"] = sorted(rename[item] for item in dependencies[step_id])
        normalized_steps.append(step)
    normalized["action"]["steps"] = normalized_steps
    return normalized


def _set_distance(left: tuple[Any, ...], right: tuple[Any, ...]) -> int:
    return len({repr(item) for item in left} ^ {repr(item) for item in right})


def _alignment_cost(candidate: CanonicalAgentRequest, gold: CanonicalAgentRequest) -> tuple[int, int, int]:
    semantic = (
        _set_distance(candidate.workflow_nodes, gold.workflow_nodes)
        + _set_distance(candidate.arguments, gold.arguments)
        + _set_distance(candidate.verification_policies, gold.verification_policies)
    )
    structural = (
        _set_distance(candidate.workflow_edges, gold.workflow_edges)
        + _set_distance(candidate.artifact_references, gold.artifact_references)
    )
    return semantic + structural, semantic, structural


def canonicalize_workflow_pair(
    candidate: str | Mapping[str, Any], gold: str | Mapping[str, Any], registry: ToolRegistry,
) -> tuple[Any, Any]:
    """Align candidate nodes to gold by minimum exact structured graph edits."""
    normalized_gold, gold_info = canonicalize_workflow_graph(gold)
    if gold_info.status == "invalid":
        raise ValueError(f"Gold workflow canonicalization failed: {gold_info.error}")
    raw_candidate = _payload(candidate)
    if gold_info.status != "canonicalized" or not isinstance(raw_candidate, Mapping):
        return raw_candidate, normalized_gold
    independently_normalized, candidate_info = canonicalize_workflow_graph(raw_candidate)
    if candidate_info.status != "canonicalized":
        return independently_normalized, normalized_gold
    candidate_ids, candidate_dependencies, candidate_by_id = _graph_parts(raw_candidate)
    canonical_ids = tuple(value for _, value in sorted(gold_info.original_to_canonical))
    if len(candidate_ids) != len(canonical_ids):
        return independently_normalized, normalized_gold
    canonical_gold = canonicalize_agent_request(normalized_gold, registry)
    if not canonical_gold.valid:
        raise ValueError(f"Gold AgentRequest is invalid after canonicalization: {canonical_gold.error}")

    best_key: tuple[Any, ...] | None = None
    best_candidate: dict[str, Any] | None = None
    for assigned_ids in itertools.permutations(sorted(canonical_ids)):
        rename = dict(zip(candidate_ids, assigned_ids))
        normalized = _normalize_with_mapping(
            raw_candidate, candidate_ids, candidate_dependencies, candidate_by_id, rename
        )
        canonical_candidate = canonicalize_agent_request(normalized, registry)
        if not canonical_candidate.valid:
            continue
        encoding = json.dumps(normalized["action"]["steps"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        key = _alignment_cost(canonical_candidate, canonical_gold) + (encoding,)
        if best_key is None or key < best_key:
            best_key, best_candidate = key, normalized
    return (best_candidate if best_candidate is not None else independently_normalized), normalized_gold


class StructuralContrastRewardV2(StructuralContrastReward):
    """Score graph-canonical requests while preserving real structural differences."""

    def __init__(self, registry: ToolRegistry) -> None:
        super().__init__(registry)

    def score(self, candidate: str | Mapping[str, Any], gold: str | Mapping[str, Any]) -> StructuralRewardBreakdown:
        normalized_candidate, normalized_gold = canonicalize_workflow_pair(candidate, gold, self.registry)
        return super().score(normalized_candidate, normalized_gold)
