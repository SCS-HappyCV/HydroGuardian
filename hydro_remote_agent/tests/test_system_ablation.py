from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.evaluation.system_ablation import run_system_ablation, transform_row


def _row(request_id: str, action_type: str, tools: list[str], verdict: str = "passed") -> dict:
    workflow = None
    if tools:
        workflow = {
            "duration_ms": 12.0,
            "warnings": [],
            "terminal_artifacts": {},
            "steps": [
                {
                    "tool": tools[0],
                    "verification_result": {
                        "status": "succeeded",
                        "duration_ms": 2.0,
                        "artifacts": {},
                        "metrics": {"verdict": verdict},
                        "warnings": [],
                    },
                }
            ],
        }
    return {
        "id": request_id,
        "status": "succeeded",
        "result": {
            "schema_version": "1.0",
            "request_id": request_id,
            "execution_id": f"exec-{request_id}",
            "status": "succeeded",
            "action_type": action_type,
            "intent": "test",
            "execution_mode": "planner_only" if not tools else "expert_runtime",
            "outcome": "response" if not tools else "result",
            "required_tools": tools,
            "terminal_artifacts": {},
            "workflow_result": workflow,
            "duration_ms": 15.0,
            "is_mock": False,
            "warnings": [],
            "error": None,
        },
    }


class SystemAblationTest(unittest.TestCase):
    def test_no_verifier_removes_only_verification(self) -> None:
        source = _row("q1", "tool_call", ["point_semantic_segmentation"])
        transformed, diagnostics = transform_row(source, "no_verifier")
        step = transformed["result"]["workflow_result"]["steps"][0]
        self.assertIsNone(step["verification_result"])
        self.assertEqual(diagnostics["removed_verifiers"], 1.0)
        self.assertEqual(transformed["result"]["duration_ms"], 13.0)
        self.assertIsNotNone(source["result"]["workflow_result"]["steps"][0]["verification_result"])

    def test_component_removal_blocks_only_affected_requests(self) -> None:
        workflow, _ = transform_row(
            _row("q1", "workflow", ["multimodal_semantic_segmentation"]),
            "no_workflow",
        )
        direct, _ = transform_row(_row("q2", "direct_answer", []), "no_workflow")
        language, _ = transform_row(
            _row("q3", "tool_call", ["language_guided_point_segmentation"]),
            "no_language_expert",
        )
        self.assertEqual(workflow["status"], "blocked")
        self.assertEqual(direct["status"], "succeeded")
        self.assertEqual(language["result"]["outcome"], "language_expert_unavailable")

    def test_run_writes_reproducible_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            predictions = root / "predictions.jsonl"
            baseline = root / "baseline.jsonl"
            output = root / "output.jsonl"
            report_path = root / "report.json"
            rows = [
                _row("q1", "direct_answer", []),
                _row("q2", "tool_call", ["language_guided_point_segmentation"]),
            ]
            with predictions.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps({"id": row["id"]}) + "\n")
            with baseline.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")

            report = run_system_ablation(
                predictions,
                baseline,
                output,
                report_path,
                "no_language_expert",
            )
            self.assertEqual(report["ablation"]["affected_request_count"], 1)
            self.assertEqual(report["metrics"]["task_success_rate"], 0.5)
            self.assertEqual(report["metrics"]["language_request_success_rate"], 0.0)
            self.assertEqual(report["baseline_metrics"]["task_success_rate"], 1.0)
            self.assertEqual(report["metric_deltas"]["task_success_rate"], -0.5)
            self.assertTrue(output.is_file())
            self.assertTrue(report_path.is_file())


if __name__ == "__main__":
    unittest.main()
