from __future__ import annotations

import json
from pathlib import Path

from hydro_remote_agent.rewards.hard_negative_mutations import generate_mutations
from hydro_remote_agent.rewards.request_canonicalizer import canonicalize_agent_request
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml")
MANIFEST = ROOT / "runs/hydro_remote_agent/vaguehydro_grpo_reward_design_v1/DATA_MANIFEST.json"


def _gold(action_type: str) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return next(item["gold_action"] for item in manifest["records"] if item["action_type"] == action_type)


def test_tool_mutations_have_expected_validity() -> None:
    mutations = generate_mutations(_gold("tool_call"))
    families = {item.family for item in mutations}
    assert {"tool_replacement", "argument_value", "argument_slot", "verification_stop", "invalid_schema"} <= families
    for item in mutations:
        assert isinstance(item.equivalence, bool)
        assert canonicalize_agent_request(item.candidate, REGISTRY).valid is item.valid_expected


def test_workflow_mutations_have_expected_validity() -> None:
    mutations = generate_mutations(_gold("workflow"))
    families = {item.family for item in mutations}
    assert {
        "tool_replacement", "argument_value", "argument_slot", "workflow_node",
        "dag_link", "artifact_reference", "verification_stop", "invalid_schema",
    } <= families
    for item in mutations:
        assert isinstance(item.equivalence, bool)
        assert canonicalize_agent_request(item.candidate, REGISTRY).valid is item.valid_expected
    assert not next(item for item in mutations if item.family == "dag_link").equivalence


def test_equivalence_controls_are_valid() -> None:
    for action_type in ("tool_call", "workflow"):
        for item in generate_mutations(_gold(action_type)):
            if item.equivalence:
                assert canonicalize_agent_request(item.candidate, REGISTRY).valid


def test_mutations_are_deterministic() -> None:
    gold = _gold("workflow")
    first = [item.to_dict() for item in generate_mutations(gold)]
    second = [item.to_dict() for item in generate_mutations(gold)]
    assert first == second
