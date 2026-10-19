from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from hydro_remote_agent.rewards.structural_contrast_reward import StructuralContrastReward
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml")
REWARD = StructuralContrastReward(REGISTRY)


def workflow_request() -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "structural:test:workflow",
        "intent": "relation_segmentation",
        "action": {
            "type": "workflow",
            "steps": [
                {
                    "step_id": "segment_a",
                    "tool": "multimodal_semantic_segmentation",
                    "arguments": {"image_path": "/tmp/a.png", "point_cloud_path": "/tmp/a.txt", "target_class_ids": [7, 14], "return_probabilities": True},
                    "depends_on": [],
                    "verification": "required",
                },
                {
                    "step_id": "segment_b",
                    "tool": "point_semantic_segmentation",
                    "arguments": {"point_cloud_path": "/tmp/a.txt", "target_class_ids": [12]},
                    "depends_on": [],
                    "verification": "required",
                },
                {
                    "step_id": "relation",
                    "tool": "geometry_relation_analysis",
                    "arguments": {"point_cloud_path": "/tmp/a.txt", "segmentation_result_path": "${segment_a.artifacts.point_labels}", "operation": "near", "target_class_id": 7, "reference_class_id": 14, "distance_threshold_m": 3.0},
                    "depends_on": ["segment_a", "segment_b"],
                    "verification": "skip",
                },
            ],
        },
        "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
    }


def tool_request() -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "structural:test:tool",
        "intent": "class_segmentation",
        "action": {
            "type": "tool_call",
            "tool": "multimodal_semantic_segmentation",
            "arguments": {"image_path": "/tmp/a.png", "point_cloud_path": "/tmp/a.txt", "target_class_ids": [7], "return_probabilities": True},
            "verification": "required",
        },
        "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
    }


def direct_request() -> dict:
    return {
        "schema_version": "1.0", "request_id": "structural:test:direct", "intent": "class_presence",
        "action": {"type": "direct_answer", "answer": "Yes. Water is present."},
        "expected_output": {"type": "text", "coordinate_space": "none"},
    }


def test_gold_exact_scores_one() -> None:
    result = REWARD.score(workflow_request(), workflow_request())
    assert result.total == pytest.approx(1.0)
    assert not result.invalid


def test_field_order_and_set_order_are_equivalent() -> None:
    gold = workflow_request()
    equivalent = json.loads(json.dumps(gold, sort_keys=True))
    equivalent["action"]["steps"][0]["arguments"]["target_class_ids"] = [14, 7]
    equivalent["action"]["steps"][2]["depends_on"] = ["segment_b", "segment_a"]
    assert REWARD.score(equivalent, gold).total == pytest.approx(1.0)


def test_parameter_perturbation_reduces_argument_value_score() -> None:
    gold = workflow_request()
    candidate = deepcopy(gold)
    candidate["action"]["steps"][2]["arguments"]["distance_threshold_m"] = 4.0
    result = REWARD.score(candidate, gold)
    assert not result.invalid
    assert result.argument_keys == pytest.approx(1.0)
    assert 0.0 < result.argument_values < 1.0
    assert result.total < 1.0


def test_valid_tool_replacement_is_distinguished() -> None:
    gold = tool_request()
    candidate = deepcopy(gold)
    candidate["action"]["tool"] = "language_guided_point_segmentation"
    candidate["action"]["arguments"]["query"] = "Segment class 7."
    result = REWARD.score(candidate, gold)
    assert not result.invalid
    assert result.tool_set == 0.0
    assert result.total < 1.0


def test_workflow_edge_and_node_perturbations_are_distinguished() -> None:
    gold = workflow_request()
    edge_candidate = deepcopy(gold)
    edge_candidate["action"]["steps"][2]["depends_on"] = ["segment_a"]
    edge_result = REWARD.score(edge_candidate, gold)
    assert not edge_result.invalid
    assert edge_result.workflow_edges < 1.0
    node_candidate = deepcopy(edge_candidate)
    del node_candidate["action"]["steps"][1]
    node_result = REWARD.score(node_candidate, gold)
    assert not node_result.invalid
    assert node_result.workflow_nodes < 1.0


def test_artifact_reference_perturbation_is_distinguished() -> None:
    gold = workflow_request()
    candidate = deepcopy(gold)
    candidate["action"]["steps"][2]["arguments"]["segmentation_result_path"] = "${segment_a.artifacts.class_masks}"
    result = REWARD.score(candidate, gold)
    assert not result.invalid
    assert result.artifact_references == 0.0
    assert result.total < 1.0


def test_stop_perturbation_is_distinguished_without_string_similarity() -> None:
    gold = direct_request()
    candidate = deepcopy(gold)
    candidate["action"]["answer"] = "No. Water is absent."
    result = REWARD.score(candidate, gold)
    assert not result.invalid
    assert result.stop == 0.0
    assert result.total == pytest.approx(0.40)


def test_invalid_schema_is_hard_zero() -> None:
    candidate = workflow_request()
    candidate["schema_version"] = "9.9"
    result = REWARD.score(candidate, workflow_request())
    assert result.invalid
    assert result.total == 0.0
