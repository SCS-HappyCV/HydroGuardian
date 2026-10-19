from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.evaluation.execution import execute_predictions, summarize_execution
from hydro_remote_agent.runtime import build_mock_runtime
from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.workflow import AgentExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"


class AgentExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)

    def _request(self, action: dict, request_id: str = "agent_exec_01") -> AgentRequest:
        return AgentRequest.from_dict(
            {
                "schema_version": "1.0",
                "request_id": request_id,
                "intent": "test_intent",
                "action": action,
            },
            self.registry,
        )

    def test_direct_answer_is_planner_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = build_mock_runtime(self.registry, root / "experts")
            result = AgentExecutor(runtime, root / "executions").execute(
                self._request({"type": "direct_answer", "answer": "present"}),
                execution_id="direct_01",
            )
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(result.execution_mode, "planner_only")
            self.assertEqual(result.outcome, "response")
            self.assertEqual(result.response, "present")
            self.assertEqual(result.required_tools, ())
            self.assertTrue(Path(result.manifest_path).is_file())

    def test_mock_tool_is_skipped_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = build_mock_runtime(self.registry, root / "experts")
            request = self._request(
                {
                    "type": "tool_call",
                    "tool": "point_semantic_segmentation",
                    "arguments": {"point_cloud_path": "tile.txt"},
                    "verification": "skip",
                }
            )
            result = AgentExecutor(runtime, root / "executions").execute(
                request,
                execution_id="mock_skip_01",
            )
            self.assertEqual(result.status, "skipped")
            self.assertEqual(result.execution_mode, "skipped_mock")
            self.assertEqual(result.outcome, "skipped_mock")
            self.assertEqual(result.error.code, "mock_expert_required")

    def test_tool_call_delegates_to_workflow_and_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = build_mock_runtime(self.registry, root / "experts")
            request = self._request(
                {
                    "type": "tool_call",
                    "tool": "point_semantic_segmentation",
                    "arguments": {"point_cloud_path": "tile.txt"},
                    "verification": "required",
                }
            )
            result = AgentExecutor(runtime, root / "executions").execute(
                request,
                execution_id="tool_01",
                skip_mock=False,
            )
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(result.execution_mode, "expert_runtime")
            self.assertEqual(result.outcome, "result")
            self.assertTrue(result.is_mock)
            self.assertIsNotNone(result.workflow_result.steps[0].verification_result)
            self.assertIn("point_labels", result.terminal_artifacts)

    def test_execution_jsonl_is_resume_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prediction_path = root / "predictions.jsonl"
            output_path = root / "results.jsonl"
            rows = [
                {
                    "id": "direct_01",
                    "prediction": json.dumps(
                        {
                            "schema_version": "1.0",
                            "request_id": "direct_01",
                            "intent": "information",
                            "action": {"type": "direct_answer", "answer": "yes"},
                        }
                    ),
                },
                {
                    "id": "tool_01",
                    "prediction": json.dumps(
                        {
                            "schema_version": "1.0",
                            "request_id": "tool_01",
                            "intent": "segmentation",
                            "action": {
                                "type": "tool_call",
                                "tool": "point_semantic_segmentation",
                                "arguments": {"point_cloud_path": "tile.txt"},
                                "verification": "skip",
                            },
                        }
                    ),
                },
            ]
            prediction_path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            runtime = build_mock_runtime(self.registry, root / "experts")
            executor = AgentExecutor(runtime, root / "executions")
            first = execute_predictions(
                prediction_path, output_path, executor, self.registry, skip_mock=True
            )
            second = execute_predictions(
                prediction_path, output_path, executor, self.registry, skip_mock=True
            )
            report = summarize_execution(prediction_path, output_path, second)
            self.assertEqual(first["written_count"], 2)
            self.assertEqual(second["resumed_count"], 2)
            self.assertEqual(second["written_count"], 0)
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["planner_succeeded_count"], 1)
            self.assertEqual(report["mock_skipped_count"], 1)
            self.assertEqual(
                report["outcome_counts"], {"response": 1, "skipped_mock": 1}
            )

    def test_failed_rows_are_retried_and_latest_attempt_is_summarized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prediction_path = root / "predictions.jsonl"
            output_path = root / "results.jsonl"
            request = {
                "schema_version": "1.0",
                "request_id": "direct_retry_01",
                "intent": "information",
                "action": {"type": "direct_answer", "answer": "yes"},
            }
            prediction_path.write_text(
                json.dumps({"id": "direct_retry_01", "prediction": request}) + "\n",
                encoding="utf-8",
            )
            output_path.write_text(
                json.dumps(
                    {
                        "id": "direct_retry_01",
                        "status": "failed",
                        "action_type": "direct_answer",
                        "required_tools": [],
                        "error": "injected",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            runtime = build_mock_runtime(self.registry, root / "experts")
            stats = execute_predictions(
                prediction_path,
                output_path,
                AgentExecutor(runtime, root / "executions"),
                self.registry,
            )
            report = summarize_execution(prediction_path, output_path, stats)
            self.assertEqual(stats["written_count"], 1)
            self.assertEqual(report["completed_count"], 1)
            self.assertEqual(report["status_counts"], {"succeeded": 1})

    def test_summary_infers_outcome_for_legacy_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prediction_path = root / "predictions.jsonl"
            output_path = root / "results.jsonl"
            prediction_path.write_text(
                json.dumps({"id": "legacy_01", "prediction": {}}) + "\n",
                encoding="utf-8",
            )
            output_path.write_text(
                json.dumps(
                    {
                        "id": "legacy_01",
                        "status": "succeeded",
                        "result": {
                            "action_type": "tool_call",
                            "execution_mode": "expert_runtime",
                            "required_tools": ["multimodal_semantic_segmentation"],
                            "terminal_artifacts": {},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            report = summarize_execution(prediction_path, output_path)
            self.assertEqual(report["outcome_counts"], {"result": 1})
            self.assertEqual(report["real_expert_result_count"], 1)


if __name__ == "__main__":
    unittest.main()
