from __future__ import annotations

import unittest
from pathlib import Path

from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.planner import SemanticPlannerBackend, normalize_expected_output


REGISTRY = Path(__file__).resolve().parents[1] / "configs" / "tool_registry.yaml"


class SemanticPlannerBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = SemanticPlannerBackend(load_tool_registry(REGISTRY))

    def plan(self, query: str, assets: dict[str, str]):
        return self.planner.plan({"request_id": "request:test", "query": query, "assets": assets})

    def test_change_detection_is_selected_from_two_period_images(self) -> None:
        plan = self.plan("对比两期影像并识别新增岸线扰动", {
            "before_image_path": "artifact://before", "after_image_path": "artifact://after",
        })
        self.assertEqual(plan["action"]["tool"], "image_change_detection")

    def test_language_guided_segmentation_extracts_classes_and_relation(self) -> None:
        plan = self.plan("找出靠近河流的沟渠", {
            "image_path": "artifact://image", "point_cloud_path": "artifact://points",
        })
        arguments = plan["action"]["arguments"]
        self.assertEqual(plan["action"]["tool"], "language_guided_point_segmentation")
        self.assertEqual(arguments["target_class_ids"], [14, 15])
        self.assertEqual(arguments["relation"], "near")
        self.assertEqual(arguments["reference_class_ids"], [15])

    def test_geometry_request_builds_dynamic_workflow(self) -> None:
        plan = self.plan("计算沟渠与河流之间的距离", {"point_cloud_path": "artifact://points"})
        self.assertEqual(plan["action"]["type"], "workflow")
        self.assertEqual([step["tool"] for step in plan["action"]["steps"]], [
            "point_semantic_segmentation", "geometry_relation_analysis",
        ])
        self.assertEqual(plan["action"]["steps"][1]["arguments"]["operation"], "pair_distance")

    def test_full_scene_with_image_still_uses_point_segmentation(self) -> None:
        plan = self.plan("执行全场景语义分割", {
            "image_path": "artifact://image", "point_cloud_path": "artifact://points",
        })
        self.assertEqual(plan["action"]["tool"], "point_semantic_segmentation")
        self.assertNotIn("image_path", plan["action"]["arguments"])

    def test_missing_assets_requests_clarification(self) -> None:
        plan = self.plan("分析这片区域", {})
        self.assertEqual(plan["action"]["type"], "clarification")

    def test_normalizes_model_expected_output_to_terminal_tool_contract(self) -> None:
        result = normalize_expected_output({
            "schema_version": "1.0",
            "request_id": "planner-repair-1",
            "intent": "change_detection",
            "action": {
                "type": "tool_call",
                "tool": "image_change_detection",
                "arguments": {"before_image_path": "before.png", "after_image_path": "after.png"},
            },
            "expected_output": {"type": "image_mask", "coordinate_space": "image_pixels"},
        }, self.planner.registry)
        self.assertEqual(result["expected_output"], {
            "type": "change_mask",
            "coordinate_space": "after_image_pixels",
        })


if __name__ == "__main__":
    unittest.main()
