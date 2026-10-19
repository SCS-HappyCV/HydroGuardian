import json
import unittest
from unittest.mock import Mock

from hydro_remote_agent.tools.run_rule_e2e_condition import (
    _execution_compatible_request,
    rule_run_record,
)


class RuleE2EConditionTest(unittest.TestCase):
    def test_frozen_multimodal_alias_maps_to_current_point_tool(self):
        request = {
            "action": {
                "type": "tool_call",
                "tool": "multimodal_semantic_segmentation",
                "arguments": {"image_path": "image.png", "point_cloud_path": "points.txt"},
            }
        }
        compatible = _execution_compatible_request(request)
        self.assertEqual(compatible["action"]["tool"], "point_semantic_segmentation")
        self.assertNotIn("image_path", compatible["action"]["arguments"])
        self.assertEqual(request["action"]["tool"], "multimodal_semantic_segmentation")

    def test_rule_request_is_executed_with_same_request_id(self):
        record = {
            "id": "request-1",
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "request_id": "request-1",
                            "query": "Segment Grassland points.",
                            "assets": {
                                "image_path": "/image.png",
                                "point_cloud_path": "/points.txt",
                            },
                        }
                    ),
                }
            ],
        }
        router = Mock()
        router.plan.return_value.request = {
            "schema_version": "1.0",
            "request_id": "request-1",
            "intent": "class_segmentation",
            "action": {"type": "direct_answer", "answer": "test"},
            "expected_output": {"type": "text", "coordinate_space": "none"},
        }
        router.plan.return_value.trace = {"latency_seconds": 0.001}
        executor = Mock()
        executor.execute_prediction.return_value = (
            {"id": "request-1", "status": "completed", "result": {}},
            router.plan.return_value.request,
            2.0,
        )
        row = rule_run_record(record, router, executor, Mock())
        self.assertEqual(row["id"], "request-1")
        self.assertEqual(row["condition"], "rule_router")
        self.assertEqual(row["execution"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
