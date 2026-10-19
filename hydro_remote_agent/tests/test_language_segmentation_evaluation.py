from __future__ import annotations

import unittest

import numpy as np

from hydro_remote_agent.evaluation.language_segmentation import (
    binary_mask_metrics,
    summarize_language_segmentation_rows,
)


class LanguageSegmentationEvaluationTest(unittest.TestCase):
    def test_binary_metrics_include_empty_match(self) -> None:
        metrics = binary_mask_metrics(np.zeros(3), np.zeros(3))
        self.assertEqual(metrics["iou"], 1.0)
        self.assertEqual(metrics["dice"], 1.0)

    def test_summary_groups_task_types_and_no_target(self) -> None:
        rows = [
            {
                "request_id": "class_1",
                "task_type": "class",
                "status": "succeeded",
                "is_no_target": False,
                "predicted_no_target": False,
                "abstained": False,
                "latency_ms": 10.0,
                "metrics": {"intersection": 2, "union": 3, "target_points": 2, "predicted_points": 3, "iou": 2 / 3, "dice": 0.8},
            },
            {
                "request_id": "none_1",
                "task_type": "no_target",
                "status": "succeeded",
                "is_no_target": True,
                "predicted_no_target": True,
                "abstained": True,
                "latency_ms": 12.0,
                "metrics": {"intersection": 0, "union": 0, "target_points": 0, "predicted_points": 0, "iou": 1.0, "dice": 1.0},
            },
        ]
        report = summarize_language_segmentation_rows(rows, expected_count=2)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["overall"]["no_target_f1"], 1.0)
        self.assertEqual(set(report["by_task_type"]), {"class", "no_target"})

    def test_summary_aggregates_threshold_sweep(self) -> None:
        rows = [
            {
                "request_id": "relation_1",
                "task_type": "relation",
                "status": "succeeded",
                "is_no_target": False,
                "predicted_no_target": False,
                "abstained": False,
                "latency_ms": 1.0,
                "metrics": binary_mask_metrics(np.asarray([1, 0]), np.asarray([0, 0])),
                "threshold_metrics": {
                    "0.1": binary_mask_metrics(np.asarray([1, 0]), np.asarray([1, 0])),
                    "0.5": binary_mask_metrics(np.asarray([1, 0]), np.asarray([0, 0])),
                },
            }
        ]

        report = summarize_language_segmentation_rows(rows, expected_count=1)

        self.assertEqual(report["threshold_sweep"]["0.1"]["overall"]["macro_iou"], 1.0)
        self.assertEqual(report["threshold_sweep"]["0.5"]["overall"]["macro_iou"], 0.0)


if __name__ == "__main__":
    unittest.main()
