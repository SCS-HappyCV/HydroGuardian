from __future__ import annotations

import json
import unittest
from pathlib import Path

from hydro_remote_agent.schemas.agent_action import (
    AgentActionError,
    AgentRequest,
    ClarificationAction,
    DirectAnswerAction,
    ToolCallAction,
    WorkflowAction,
    load_agent_request,
)
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"
EXAMPLES_PATH = PACKAGE_ROOT / "examples" / "agent_actions"


class AgentActionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)

    def _workflow_payload(self) -> dict:
        with (EXAMPLES_PATH / "workflow.json").open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def test_all_action_examples_are_valid(self) -> None:
        requests = {
            path.stem: load_agent_request(path, self.registry)
            for path in EXAMPLES_PATH.glob("*.json")
        }
        self.assertEqual(
            set(requests),
            {"abstain", "clarification", "direct_answer", "tool_call", "workflow"},
        )
        self.assertIsInstance(requests["direct_answer"].action, DirectAnswerAction)
        self.assertIsInstance(requests["clarification"].action, ClarificationAction)
        self.assertIsInstance(requests["tool_call"].action, ToolCallAction)
        self.assertIsInstance(requests["workflow"].action, WorkflowAction)

    def test_tool_call_rejects_unknown_tool(self) -> None:
        payload = {
            "schema_version": "1.0",
            "request_id": "unknown_tool_01",
            "intent": "segmentation",
            "action": {"type": "tool_call", "tool": "invented_tool", "arguments": {}},
        }
        with self.assertRaisesRegex(AgentActionError, "unknown tool"):
            AgentRequest.from_dict(payload, self.registry)

    def test_tool_call_rejects_invalid_arguments(self) -> None:
        payload = {
            "schema_version": "1.0",
            "request_id": "bad_args_01",
            "intent": "segmentation",
            "action": {
                "type": "tool_call",
                "tool": "point_semantic_segmentation",
                "arguments": {"point_cloud_path": "tile.txt", "target_class_ids": [16]},
            },
        }
        with self.assertRaisesRegex(AgentActionError, "must be <= 15"):
            AgentRequest.from_dict(payload, self.registry)

    def test_workflow_rejects_duplicate_step_ids(self) -> None:
        payload = self._workflow_payload()
        payload["action"]["steps"][1]["step_id"] = "segment"
        with self.assertRaisesRegex(AgentActionError, "duplicate step IDs"):
            AgentRequest.from_dict(payload, self.registry)

    def test_workflow_step_id_matches_reference_syntax(self) -> None:
        payload = self._workflow_payload()
        payload["action"]["steps"][0]["step_id"] = "segment.invalid"
        with self.assertRaisesRegex(AgentActionError, "invalid identifier format"):
            AgentRequest.from_dict(payload, self.registry)

    def test_workflow_rejects_excessively_long_step_id(self) -> None:
        payload = self._workflow_payload()
        payload["action"]["steps"][0]["step_id"] = "s" * 49
        with self.assertRaisesRegex(AgentActionError, "invalid identifier format"):
            AgentRequest.from_dict(payload, self.registry)

    def test_workflow_rejects_forward_dependency(self) -> None:
        payload = self._workflow_payload()
        payload["action"]["steps"][0]["depends_on"] = ["relation"]
        with self.assertRaisesRegex(AgentActionError, "must reference earlier steps"):
            AgentRequest.from_dict(payload, self.registry)

    def test_workflow_reference_requires_declared_dependency(self) -> None:
        payload = self._workflow_payload()
        payload["action"]["steps"][1]["depends_on"] = []
        with self.assertRaisesRegex(AgentActionError, "without declaring it in depends_on"):
            AgentRequest.from_dict(payload, self.registry)

    def test_workflow_rejects_unknown_artifact(self) -> None:
        payload = self._workflow_payload()
        payload["action"]["steps"][1]["arguments"]["segmentation_result_path"] = (
            "${segment.artifacts.invented_artifact}"
        )
        with self.assertRaisesRegex(AgentActionError, "unknown artifact"):
            AgentRequest.from_dict(payload, self.registry)

    def test_required_verification_needs_registered_verifier(self) -> None:
        payload = {
            "schema_version": "1.0",
            "request_id": "quality_cannot_verify_itself",
            "intent": "quality_verification",
            "action": {
                "type": "tool_call",
                "tool": "result_quality_verification",
                "arguments": {
                    "result_path": "result.json",
                    "source_tool": "geometry_relation_analysis",
                },
                "verification": "required",
            },
        }
        with self.assertRaisesRegex(AgentActionError, "has no registered verifier"):
            AgentRequest.from_dict(payload, self.registry)

    def test_expected_output_must_match_tool_contract(self) -> None:
        payload = {
            "schema_version": "1.0",
            "request_id": "bad_output_01",
            "intent": "change_detection",
            "action": {
                "type": "tool_call",
                "tool": "image_change_detection",
                "arguments": {
                    "before_image_path": "before.png",
                    "after_image_path": "after.png",
                },
            },
            "expected_output": {
                "type": "point_labels",
                "coordinate_space": "source_point_cloud",
            },
        }
        with self.assertRaisesRegex(AgentActionError, "incompatible"):
            AgentRequest.from_dict(payload, self.registry)

    def test_direct_answer_requires_text_output(self) -> None:
        payload = {
            "schema_version": "1.0",
            "request_id": "bad_direct_01",
            "intent": "information",
            "action": {"type": "direct_answer", "answer": "answer"},
            "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
        }
        with self.assertRaisesRegex(AgentActionError, "can only satisfy"):
            AgentRequest.from_dict(payload, self.registry)


if __name__ == "__main__":
    unittest.main()
