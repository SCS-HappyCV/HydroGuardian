from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.evaluation.execution import merge_execution_results, summarize_execution


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class ExecutionResultMergeTest(unittest.TestCase):
    def test_summary_records_verifier_verdict_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            predictions = root / "predictions.jsonl"
            results = root / "results.jsonl"
            _write_jsonl(predictions, [{"id": "a", "prediction": "{}"}])
            _write_jsonl(
                results,
                [
                    {
                        "id": "a",
                        "status": "succeeded",
                        "result": {
                            "action_type": "tool_call",
                            "execution_mode": "expert_runtime",
                            "is_mock": False,
                            "required_tools": ["point_semantic_segmentation"],
                            "terminal_artifacts": {},
                            "workflow_result": {
                                "steps": [
                                    {
                                        "verification_result": {
                                            "status": "succeeded",
                                            "metrics": {"verdict": "warning"},
                                        }
                                    }
                                ]
                            },
                        },
                    }
                ],
            )
            report = summarize_execution(predictions, results)
            self.assertEqual(report["verifier_verdict_counts"], {"warning": 1})

    def test_replaces_exact_skipped_set_in_prediction_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            predictions = root / "predictions.jsonl"
            base = root / "base.jsonl"
            replacements = root / "replacements.jsonl"
            output = root / "output.jsonl"
            _write_jsonl(predictions, [{"id": "a", "prediction": "{}"}, {"id": "b", "prediction": "{}"}])
            _write_jsonl(base, [
                {"id": "a", "status": "succeeded", "result": {"execution_mode": "planner_only"}},
                {"id": "b", "status": "skipped", "result": {"execution_mode": "skipped_mock"}},
            ])
            _write_jsonl(replacements, [
                {"id": "b", "status": "succeeded", "result": {"execution_mode": "expert_runtime", "is_mock": False}},
            ])
            manifest = merge_execution_results(predictions, base, replacements, output)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["id"] for row in rows], ["a", "b"])
            self.assertEqual(rows[1]["result"]["execution_mode"], "expert_runtime")
            self.assertEqual(manifest["replacement_count"], 1)

    def test_rejects_incomplete_replacement_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            predictions = root / "predictions.jsonl"
            base = root / "base.jsonl"
            replacements = root / "replacements.jsonl"
            _write_jsonl(predictions, [{"id": "a", "prediction": "{}"}])
            _write_jsonl(base, [{"id": "a", "status": "skipped", "result": {"execution_mode": "skipped_mock"}}])
            _write_jsonl(replacements, [])
            with self.assertRaisesRegex(ValueError, "exactly match"):
                merge_execution_results(predictions, base, replacements, root / "output.jsonl")


if __name__ == "__main__":
    unittest.main()
