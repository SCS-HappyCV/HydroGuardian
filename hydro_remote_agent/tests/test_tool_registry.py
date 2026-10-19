from __future__ import annotations

import unittest
from pathlib import Path

from hydro_remote_agent.schemas.tool_spec import (
    ToolArgumentError,
    ToolRegistry,
    ToolSpecError,
    load_tool_registry,
)


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "configs" / "tool_registry.yaml"
EXPECTED_TOOLS = {
    "point_semantic_segmentation",
    "multimodal_semantic_segmentation",
    "image_change_detection",
    "language_guided_point_segmentation",
    "geometry_relation_analysis",
    "result_quality_verification",
}


class ToolRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)

    def test_registry_contains_exactly_six_core_experts(self) -> None:
        self.assertEqual(set(self.registry.names()), EXPECTED_TOOLS)
        self.assertEqual(len(self.registry.tools), 6)

    def test_analysis_tools_use_quality_verifier(self) -> None:
        analysis_tools = EXPECTED_TOOLS - {"result_quality_verification"}
        for name in analysis_tools:
            self.assertEqual(self.registry.get(name).verifier, "result_quality_verification")

    def test_relation_tool_is_deterministic(self) -> None:
        relation_tool = self.registry.get("geometry_relation_analysis")
        self.assertTrue(relation_tool.deterministic)
        self.assertIn("point_cloud", relation_tool.required_modalities)
        self.assertIn("segmentation_prediction", relation_tool.required_modalities)

    def test_openai_tool_conversion_preserves_argument_schema(self) -> None:
        tool = self.registry.get("language_guided_point_segmentation")
        converted = tool.to_openai_tool()
        self.assertEqual(converted["type"], "function")
        self.assertEqual(converted["function"]["name"], tool.name)
        self.assertEqual(converted["function"]["parameters"], tool.arguments_schema)

    def test_valid_tool_arguments_are_accepted(self) -> None:
        tool = self.registry.get("geometry_relation_analysis")
        tool.validate_arguments(
            {
                "point_cloud_path": "tile.txt",
                "segmentation_result_path": "labels.npz",
                "operation": "near",
                "target_class_id": 4,
                "reference_class_id": 13,
                "distance_threshold_m": 3.0,
            }
        )

    def test_invalid_tool_arguments_are_rejected(self) -> None:
        tool = self.registry.get("image_change_detection")
        with self.assertRaises(ToolArgumentError):
            tool.validate_arguments(
                {
                    "before_image_path": "before.png",
                    "after_image_path": "after.png",
                    "change_threshold": 1.5,
                }
            )

    def test_unknown_argument_is_rejected(self) -> None:
        tool = self.registry.get("point_semantic_segmentation")
        with self.assertRaises(ToolArgumentError):
            tool.validate_arguments(
                {
                    "point_cloud_path": "tile.txt",
                    "invented_parameter": True,
                }
            )

    def test_duplicate_tool_names_are_rejected(self) -> None:
        tool = {
            "name": "example_tool",
            "version": "1.0",
            "description": "Example.",
            "capabilities": ["example"],
            "inputs": {"required_modalities": [], "optional_modalities": []},
            "arguments_schema": {"type": "object", "properties": {}, "required": []},
            "output": {"result_types": ["quality_report"], "coordinate_space": "none"},
            "resources": {},
        }
        with self.assertRaises(ToolSpecError):
            ToolRegistry.from_dict({"schema_version": "1.0", "tools": [tool, tool]})

    def test_unknown_verifier_is_rejected(self) -> None:
        tool = {
            "name": "example_tool",
            "version": "1.0",
            "description": "Example.",
            "capabilities": ["example"],
            "inputs": {"required_modalities": [], "optional_modalities": []},
            "arguments_schema": {"type": "object", "properties": {}, "required": []},
            "output": {"result_types": ["quality_report"], "coordinate_space": "none"},
            "resources": {},
            "verifier": "missing_verifier",
        }
        with self.assertRaises(ToolSpecError):
            ToolRegistry.from_dict({"schema_version": "1.0", "tools": [tool]})


if __name__ == "__main__":
    unittest.main()
