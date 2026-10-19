from __future__ import annotations

import unittest

from hydro_remote_agent.evaluation.language_calibration import (
    calibrate_no_target,
    select_mask_thresholds,
)


class LanguageCalibrationTest(unittest.TestCase):
    def test_selects_best_mask_threshold_per_task(self) -> None:
        rows = [
            {
                "status": "succeeded",
                "task_type": "relation",
                "runtime_task_type": "relation",
                "threshold_metrics": {
                    "0.1": {"intersection": 2, "union": 2, "iou": 1.0, "dice": 1.0},
                    "0.5": {"intersection": 0, "union": 2, "iou": 0.0, "dice": 0.0},
                },
            }
        ]

        report = select_mask_thresholds(rows)

        self.assertEqual(report["relation"]["best"]["threshold"], 0.1)

    def test_calibrates_no_target_from_validation_diagnostics(self) -> None:
        rows = []
        for task_type, posterior, probability_max in (
            ("no_target", 0.8, 0.05),
            ("no_target", 0.7, 0.08),
            ("class", 0.2, 0.9),
            ("class", 0.1, 0.8),
        ):
            rows.append(
                {
                    "status": "succeeded",
                    "task_type": task_type,
                    "runtime_task_type": "class",
                    "is_no_target": task_type == "no_target",
                    "diagnostics": {
                        "posterior_no_target_mass": posterior,
                        "abstain_probability": posterior,
                        "probability_max": probability_max,
                    },
                }
            )

        report = calibrate_no_target(rows)

        self.assertEqual(report["request_count"], 4)
        self.assertEqual(report["best_rule"]["metrics"]["f1"], 1.0)

    def test_mask_thresholds_group_by_runtime_program_type(self) -> None:
        rows = [
            {
                "status": "succeeded",
                "task_type": "attribute",
                "runtime_task_type": "class",
                "threshold_metrics": {
                    "0.1": {"intersection": 1, "union": 1, "iou": 1.0, "dice": 1.0},
                    "0.2": {"intersection": 0, "union": 1, "iou": 0.0, "dice": 0.0},
                },
            }
        ]

        report = select_mask_thresholds(rows)

        self.assertEqual(set(report), {"class"})
        self.assertEqual(report["class"]["best"]["threshold"], 0.1)

    def test_mask_thresholds_exclude_no_target_rows(self) -> None:
        rows = [
            {
                "status": "succeeded",
                "task_type": "no_target",
                "runtime_task_type": "class",
                "is_no_target": True,
                "threshold_metrics": {
                    "0.5": {"intersection": 0, "union": 0, "iou": 1.0, "dice": 1.0},
                },
            }
        ]

        self.assertEqual(select_mask_thresholds(rows), {})


if __name__ == "__main__":
    unittest.main()
