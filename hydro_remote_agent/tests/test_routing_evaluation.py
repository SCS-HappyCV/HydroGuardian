from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.evaluation.routing import (
    RoutingEvaluationError,
    evaluate_routing,
    parse_json_response,
)
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"


def _request(query_id: str = "q:test") -> dict:
    return {
        "schema_version": "1.0",
        "request_id": query_id,
        "intent": "class_segmentation",
        "action": {
            "type": "tool_call",
            "tool": "point_semantic_segmentation",
            "arguments": {
                "point_cloud_path": "tile.txt",
                "target_class_ids": [9],
            },
        },
        "expected_output": {
            "type": "point_mask",
            "coordinate_space": "source_point_cloud",
        },
    }


def _gold_row(query_id: str, request: dict, language: str = "en", level: str = "L2") -> dict:
    return {
        "id": query_id,
        "split": "test",
        "language": language,
        "ambiguity_level": level,
        "messages": [
            {"role": "system", "content": "planner"},
            {"role": "user", "content": "query"},
            {"role": "assistant", "content": json.dumps(request)},
        ],
    }


def _workflow_request(query_id: str = "q:workflow") -> dict:
    return {
        "schema_version": "1.0",
        "request_id": query_id,
        "intent": "relation_segmentation",
        "action": {
            "type": "workflow",
            "steps": [
                {
                    "step_id": "segment",
                    "tool": "point_semantic_segmentation",
                    "arguments": {
                        "point_cloud_path": "tile.txt",
                        "target_class_ids": [4, 9],
                    },
                },
                {
                    "step_id": "relation",
                    "tool": "geometry_relation_analysis",
                    "depends_on": ["segment"],
                    "arguments": {
                        "point_cloud_path": "tile.txt",
                        "segmentation_result_path": "${segment.artifacts.point_labels}",
                        "operation": "near",
                        "target_class_id": 4,
                        "reference_class_id": 9,
                    },
                },
            ],
        },
        "expected_output": {
            "type": "point_mask",
            "coordinate_space": "source_point_cloud",
        },
    }


class RoutingEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_tool_registry(REGISTRY_PATH)

    def _evaluate(self, gold_rows: list, prediction_rows: list) -> dict:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gold_path = root / "gold.jsonl"
            prediction_path = root / "predictions.jsonl"
            gold_path.write_text(
                "".join(json.dumps(row) + "\n" for row in gold_rows),
                encoding="utf-8",
            )
            prediction_path.write_text(
                "".join(json.dumps(row) + "\n" for row in prediction_rows),
                encoding="utf-8",
            )
            return evaluate_routing([gold_path], prediction_path, self.registry)

    def test_oracle_predictions_score_one(self) -> None:
        request = _request()
        report = self._evaluate(
            [_gold_row("q:test", request)],
            [{"id": "q:test", "prediction": request}],
        )
        metrics = report["metrics"]
        self.assertEqual(metrics["schema_valid_rate"], 1.0)
        self.assertEqual(metrics["action_type_accuracy"], 1.0)
        self.assertEqual(metrics["tool_selection_accuracy"], 1.0)
        self.assertEqual(metrics["argument_slot_f1"], 1.0)
        self.assertEqual(report["by_language"]["en"]["count"], 1)
        self.assertEqual(report["by_gold_action_type"]["tool_call"]["count"], 1)

    def test_invalid_json_scores_zero_and_is_reported(self) -> None:
        request = _request()
        report = self._evaluate(
            [_gold_row("q:test", request)],
            [{"id": "q:test", "prediction": "not-json"}],
        )
        self.assertEqual(report["metrics"]["parse_rate"], 0.0)
        self.assertEqual(report["metrics"]["schema_valid_rate"], 0.0)
        self.assertEqual(report["metrics"]["action_type_accuracy"], 0.0)
        self.assertEqual(report["metrics"]["argument_slot_f1"], 0.0)
        self.assertEqual(len(report["error_examples"]), 1)

    def test_wrong_argument_reduces_slot_f1(self) -> None:
        gold = _request()
        prediction = copy.deepcopy(gold)
        prediction["action"]["arguments"]["target_class_ids"] = [11]
        report = self._evaluate(
            [_gold_row("q:test", gold)],
            [{"id": "q:test", "prediction": prediction}],
        )
        metrics = report["metrics"]
        self.assertEqual(metrics["tool_selection_accuracy"], 1.0)
        self.assertLess(metrics["argument_slot_f1"], 1.0)
        self.assertEqual(metrics["request_exact_match"], 0.0)

    def test_missing_and_extra_predictions_are_counted(self) -> None:
        request = _request()
        report = self._evaluate(
            [_gold_row("q:test", request)],
            [{"id": "q:extra", "prediction": _request("q:extra")}],
        )
        self.assertEqual(report["missing_prediction_count"], 1)
        self.assertEqual(report["extra_prediction_count"], 1)
        self.assertEqual(report["metrics"]["schema_valid_rate"], 0.0)

    def test_duplicate_prediction_ids_are_rejected(self) -> None:
        request = _request()
        with self.assertRaisesRegex(RoutingEvaluationError, "duplicates prediction"):
            self._evaluate(
                [_gold_row("q:test", request)],
                [
                    {"id": "q:test", "prediction": request},
                    {"id": "q:test", "prediction": request},
                ],
            )

    def test_fenced_json_response_is_supported(self) -> None:
        parsed = parse_json_response("```json\n" + json.dumps(_request()) + "\n```")
        self.assertEqual(parsed["action"]["type"], "tool_call")

    def test_plain_json_language_prefix_is_supported(self) -> None:
        parsed = parse_json_response("json\n" + json.dumps(_request()))
        self.assertEqual(parsed["action"]["type"], "tool_call")

    def test_workflow_dependency_error_reduces_graph_accuracy(self) -> None:
        gold = _workflow_request()
        prediction = copy.deepcopy(gold)
        prediction["action"]["steps"][1]["depends_on"] = []
        prediction["action"]["steps"][1]["arguments"]["segmentation_result_path"] = "labels.txt"
        report = self._evaluate(
            [_gold_row("q:workflow", gold)],
            [{"id": "q:workflow", "prediction": prediction}],
        )
        self.assertEqual(report["metrics"]["schema_valid_rate"], 1.0)
        self.assertEqual(report["metrics"]["tool_selection_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["workflow_graph_accuracy"], 0.0)

    def test_cluster_bootstrap_is_deterministic(self) -> None:
        request = _request()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gold_path = root / "gold.jsonl"
            prediction_path = root / "predictions.jsonl"
            row = _gold_row("q:test", request)
            row["sample_id"] = "sample:test"
            gold_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            prediction_path.write_text(
                json.dumps({"id": "q:test", "prediction": request}) + "\n",
                encoding="utf-8",
            )
            report = evaluate_routing(
                [gold_path],
                prediction_path,
                self.registry,
                bootstrap_samples=50,
                bootstrap_seed=11,
            )
        bootstrap = report["bootstrap"]
        self.assertEqual(bootstrap["cluster_count"], 1)
        self.assertEqual(bootstrap["samples"], 50)
        self.assertEqual(
            bootstrap["metrics"]["action_type_accuracy"],
            {"lower": 1.0, "upper": 1.0},
        )
        wilson = report["binomial_confidence_intervals"]["metrics"][
            "action_type_accuracy"
        ]
        self.assertLess(wilson["lower"], 1.0)
        self.assertEqual(wilson["upper"], 1.0)


if __name__ == "__main__":
    unittest.main()
