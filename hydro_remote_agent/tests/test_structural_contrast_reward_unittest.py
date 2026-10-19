from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from hydro_remote_agent.rewards.structural_contrast_reward import StructuralContrastReward
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


ROOT = Path(__file__).resolve().parents[2]
REWARD = StructuralContrastReward(load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml"))


def workflow_request() -> dict:
    return {
        "schema_version": "1.0", "request_id": "structural:test:workflow", "intent": "relation_segmentation",
        "action": {"type": "workflow", "steps": [
            {"step_id": "segment_a", "tool": "multimodal_semantic_segmentation", "arguments": {"image_path": "/tmp/a.png", "point_cloud_path": "/tmp/a.txt", "target_class_ids": [7, 14], "return_probabilities": True}, "depends_on": [], "verification": "required"},
            {"step_id": "segment_b", "tool": "point_semantic_segmentation", "arguments": {"point_cloud_path": "/tmp/a.txt", "target_class_ids": [12]}, "depends_on": [], "verification": "required"},
            {"step_id": "relation", "tool": "geometry_relation_analysis", "arguments": {"point_cloud_path": "/tmp/a.txt", "segmentation_result_path": "${segment_a.artifacts.point_labels}", "operation": "near", "target_class_id": 7, "reference_class_id": 14, "distance_threshold_m": 3.0}, "depends_on": ["segment_a", "segment_b"], "verification": "skip"}
        ]},
        "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
    }


def tool_request() -> dict:
    return {
        "schema_version": "1.0", "request_id": "structural:test:tool", "intent": "class_segmentation",
        "action": {"type": "tool_call", "tool": "multimodal_semantic_segmentation", "arguments": {"image_path": "/tmp/a.png", "point_cloud_path": "/tmp/a.txt", "target_class_ids": [7], "return_probabilities": True}, "verification": "required"},
        "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
    }


class StructuralContrastRewardTests(unittest.TestCase):
    def test_gold_exact(self) -> None:
        self.assertAlmostEqual(REWARD.score(workflow_request(), workflow_request()).total, 1.0)

    def test_field_order_equivalent(self) -> None:
        gold = workflow_request(); candidate = json.loads(json.dumps(gold, sort_keys=True))
        candidate["action"]["steps"][0]["arguments"]["target_class_ids"] = [14, 7]
        candidate["action"]["steps"][2]["depends_on"] = ["segment_b", "segment_a"]
        self.assertAlmostEqual(REWARD.score(candidate, gold).total, 1.0)

    def test_parameter_perturbation(self) -> None:
        gold = workflow_request(); candidate = deepcopy(gold)
        candidate["action"]["steps"][2]["arguments"]["distance_threshold_m"] = 4.0
        result = REWARD.score(candidate, gold)
        self.assertFalse(result.invalid); self.assertLess(result.argument_values, 1.0); self.assertLess(result.total, 1.0)

    def test_tool_replacement(self) -> None:
        gold = tool_request(); candidate = deepcopy(gold)
        candidate["action"]["tool"] = "language_guided_point_segmentation"; candidate["action"]["arguments"]["query"] = "Segment class 7."
        result = REWARD.score(candidate, gold)
        self.assertFalse(result.invalid); self.assertEqual(result.tool_set, 0.0); self.assertLess(result.total, 1.0)

    def test_dag_edge_and_node(self) -> None:
        gold = workflow_request(); edge = deepcopy(gold); edge["action"]["steps"][2]["depends_on"] = ["segment_a"]
        edge_result = REWARD.score(edge, gold); self.assertFalse(edge_result.invalid); self.assertLess(edge_result.workflow_edges, 1.0)
        node = deepcopy(edge); del node["action"]["steps"][1]
        node_result = REWARD.score(node, gold); self.assertFalse(node_result.invalid); self.assertLess(node_result.workflow_nodes, 1.0)

    def test_artifact_reference(self) -> None:
        gold = workflow_request(); candidate = deepcopy(gold)
        candidate["action"]["steps"][2]["arguments"]["segmentation_result_path"] = "${segment_a.artifacts.class_masks}"
        result = REWARD.score(candidate, gold); self.assertFalse(result.invalid); self.assertEqual(result.artifact_references, 0.0)

    def test_stop_perturbation(self) -> None:
        gold = {"schema_version": "1.0", "request_id": "structural:test:direct", "intent": "class_presence", "action": {"type": "direct_answer", "answer": "Yes."}, "expected_output": {"type": "text", "coordinate_space": "none"}}
        candidate = deepcopy(gold); candidate["action"]["answer"] = "No."
        result = REWARD.score(candidate, gold); self.assertEqual(result.stop, 0.0); self.assertAlmostEqual(result.total, 0.4)

    def test_invalid_schema(self) -> None:
        candidate = workflow_request(); candidate["schema_version"] = "9.9"
        result = REWARD.score(candidate, workflow_request()); self.assertTrue(result.invalid); self.assertEqual(result.total, 0.0)


if __name__ == "__main__":
    unittest.main()
