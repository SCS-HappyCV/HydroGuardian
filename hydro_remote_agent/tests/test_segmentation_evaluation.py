from __future__ import annotations

import unittest

import numpy as np

from hydro_remote_agent.evaluation.segmentation import (
    confusion_matrix_1based,
    segmentation_metrics,
    summarize_segmentation_rows,
)


class SegmentationEvaluationTest(unittest.TestCase):
    def test_confusion_and_metrics(self) -> None:
        confusion = confusion_matrix_1based(
            np.asarray([1, 1, 2, 2]), np.asarray([1, 2, 2, 2]), num_classes=2
        )
        np.testing.assert_array_equal(confusion, [[1, 1], [0, 2]])
        metrics = segmentation_metrics(confusion)
        self.assertAlmostEqual(metrics["mean_iou"], (0.5 + 2.0 / 3.0) / 2.0)
        self.assertEqual(metrics["mean_accuracy"], 0.75)
        self.assertEqual(metrics["overall_accuracy"], 0.75)
        self.assertEqual(metrics["per_class"][0]["accuracy"], 0.5)
        self.assertEqual(metrics["per_class"][1]["accuracy"], 1.0)

    def test_summary_is_partial_when_a_tile_failed(self) -> None:
        confusion = np.zeros((15, 15), dtype=np.int64)
        confusion[0, 0] = 3
        report = summarize_segmentation_rows(
            [
                {
                    "sample_id": "ok",
                    "status": "succeeded",
                    "latency_ms": 10,
                    "confusion_matrix": confusion.tolist(),
                },
                {"sample_id": "bad", "status": "failed", "error": "failure"},
            ],
            expected_count=2,
        )
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["failed_count"], 1)


if __name__ == "__main__":
    unittest.main()
