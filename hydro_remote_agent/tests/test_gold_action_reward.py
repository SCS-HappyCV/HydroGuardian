from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward, _value_score
from hydro_remote_agent.rewards.request_canonicalizer import canonicalize_agent_request
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml")


def workflow_request() -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "reward:test:workflow",
        "intent": "relation_analysis",
        "action": {
            "type": "workflow",
            "steps": [
                {
                    "step_id": "segment_a",
                    "tool": "point_semantic_segmentation",
                    "arguments": {"point_cloud_path": "/tmp/a.txt", "target_class_ids": [7]},
                    "depends_on": [],
                    "verification": "required",
                },
                {
                    "step_id": "segment_b",
                    "tool": "point_semantic_segmentation",
                    "arguments": {"point_cloud_path": "/tmp/a.txt", "target_class_ids": [14]},
                    "depends_on": [],
                    "verification": "required",
                },
                {
                    "step_id": "relation",
                    "tool": "geometry_relation_analysis",
                    "arguments": {
                        "point_cloud_path": "/tmp/a.txt",
                        "segmentation_result_path": "${segment_a.artifacts.point_labels}",
                        "operation": "near",
                        "target_class_id": 7,
                        "reference_class_id": 14,
                    },
                    "depends_on": ["segment_a", "segment_b"],
                    "verification": "required",
                },
            ],
        },
        "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
    }


def clarification_request() -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "reward:test:clarification",
        "intent": "missing_asset",
        "action": {
            "type": "clarification",
            "question": "请补充前时相影像。",
            "missing_fields": ["before_image_path"],
        },
        "expected_output": {"type": "text", "coordinate_space": "none"},
    }


def abstain_request() -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "reward:test:abstain",
        "intent": "unsupported",
        "action": {
            "type": "abstain",
            "reason": "当前专家不支持该任务。",
            "error_code": "unsupported_capability",
            "recoverable": False,
        },
        "expected_output": {"type": "text", "coordinate_space": "none"},
    }


def test_field_order_and_equivalent_workflow_order_score_one() -> None:
    gold = workflow_request()
    equivalent = deepcopy(gold)
    equivalent["action"]["steps"] = [
        equivalent["action"]["steps"][1],
        equivalent["action"]["steps"][0],
        equivalent["action"]["steps"][2],
    ]
    equivalent = json.loads(json.dumps(equivalent, sort_keys=True))
    reward = GoldActionReward(REGISTRY).score(equivalent, gold)
    assert reward.total == pytest.approx(1.0)
    assert reward.workflow == pytest.approx(1.0)


def test_unknown_tool_is_invalid() -> None:
    candidate = workflow_request()
    candidate["action"]["steps"][0]["tool"] = "unknown_tool"
    result = GoldActionReward(REGISTRY).score(candidate, workflow_request())
    assert result.invalid
    assert result.total == 0.0


@pytest.mark.parametrize("failure", ("cycle", "unknown_dependency"))
def test_invalid_dependencies_are_invalid(failure: str) -> None:
    candidate = workflow_request()
    if failure == "cycle":
        candidate["action"]["steps"][0]["depends_on"] = ["relation"]
    else:
        candidate["action"]["steps"][-1]["depends_on"] = ["missing"]
    result = GoldActionReward(REGISTRY).score(candidate, workflow_request())
    assert result.invalid


def test_missing_required_argument_is_invalid() -> None:
    candidate = workflow_request()
    del candidate["action"]["steps"][0]["arguments"]["point_cloud_path"]
    result = GoldActionReward(REGISTRY).score(candidate, workflow_request())
    assert result.invalid


def test_allowed_clarification_receives_partial_action_credit() -> None:
    result = GoldActionReward(REGISTRY).score(
        clarification_request(),
        abstain_request(),
        allowed_actions=["clarification", "abstain"],
    )
    assert not result.invalid
    assert result.action == 0.5
    assert result.tool == 0.0
    assert result.argument == 0.0
    assert result.workflow == 0.0
    assert result.stop == 0.0
    assert result.total == pytest.approx(0.3)


def test_allowed_abstain_receives_partial_action_credit() -> None:
    result = GoldActionReward(REGISTRY).score(
        abstain_request(),
        clarification_request(),
        allowed_actions=["clarification", "abstain"],
    )
    assert not result.invalid
    assert result.action == 0.5


def test_invalid_json_is_invalid() -> None:
    result = GoldActionReward(REGISTRY).score("{not-json", clarification_request())
    assert result.invalid
    assert result.schema == 0.0


def test_set_arguments_are_order_invariant() -> None:
    gold = workflow_request()
    candidate = deepcopy(gold)
    candidate["action"]["steps"][-1]["depends_on"] = ["segment_b", "segment_a"]
    gold_canonical = canonicalize_agent_request(gold, REGISTRY)
    candidate_canonical = canonicalize_agent_request(candidate, REGISTRY)
    assert candidate_canonical.valid
    assert candidate_canonical.workflow_edges == gold_canonical.workflow_edges
    assert GoldActionReward(REGISTRY).score(candidate, gold).total == pytest.approx(1.0)


def test_time_and_class_identifiers_require_exact_match() -> None:
    assert _value_score("arguments.timestamp", 12, 12) == 1.0
    assert _value_score("arguments.timestamp", 12.01, 12) == 0.0
    assert _value_score("arguments.class_id", 7, 7) == 1.0
    assert _value_score("arguments.class_id", 8, 7) == 0.0


def test_continuous_numeric_error_is_smooth() -> None:
    exact = _value_score("arguments.threshold", 0.5, 0.5)
    close = _value_score("arguments.threshold", 0.55, 0.5)
    far = _value_score("arguments.threshold", 1.0, 0.5)
    assert exact == 1.0
    assert 0.0 < far < close < exact


def test_spatial_iou_and_relation_predicates() -> None:
    assert _value_score("arguments.bbox", [0, 0, 2, 2], [0, 0, 2, 2]) == 1.0
    assert _value_score("arguments.bbox", [0, 0, 1, 1], [0, 0, 2, 2]) == pytest.approx(0.25)
    assert _value_score(
        "arguments.spatial_relation_predicates",
        ["above", "near"],
        ["near", "above"],
    ) == 1.0
