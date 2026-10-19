from __future__ import annotations

import unittest

from hydro_remote_agent.evaluation.service_reliability import (
    build_service_report,
    latency_summary,
)


class ServiceReliabilityEvaluationTest(unittest.TestCase):
    def test_latency_summary(self) -> None:
        summary = latency_summary([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(summary["count"], 4)
        self.assertEqual(summary["mean_ms"], 2.5)
        self.assertEqual(summary["p50_ms"], 2.5)

    def test_report_fails_when_a_check_fails(self) -> None:
        report = build_service_report(
            run_id="test",
            health_latencies_ms=[1.0],
            submission_latencies_ms=[2.0],
            end_to_end_latencies_ms=[3.0],
            jobs=[{"status": "succeeded"}],
            checks={"ok": True, "bad": False},
            recovery={},
        )
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["failed_checks"], ["bad"])
        self.assertEqual(report["metrics"]["terminal_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
