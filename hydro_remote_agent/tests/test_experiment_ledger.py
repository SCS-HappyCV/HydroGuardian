from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.evaluation.experiment_ledger import collect_experiment_ledger


class ExperimentLedgerTest(unittest.TestCase):
    def test_collects_completed_and_missing_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "report.json"
            report_path.write_text(
                json.dumps({"schema_version": "report.v1", "metrics": {"count": 2, "score": 1.0}}),
                encoding="utf-8",
            )
            protocol_path = root / "protocol.json"
            protocol_path.write_text(
                json.dumps(
                    {
                        "schema_version": "vague_hydro.experiment_protocol.v1",
                        "protocol_id": "test",
                        "split": {},
                        "claims": {},
                        "runs": [
                            {
                                "run_id": "done",
                                "kind": "routing",
                                "role": "formal_method",
                                "expected_count": 2,
                                "report": "report.json",
                                "metric_paths": ["metrics.score"],
                            },
                            {
                                "run_id": "missing",
                                "kind": "routing",
                                "role": "formal_method",
                                "expected_count": 2,
                                "report": "missing.json",
                                "metric_paths": [],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            ledger = collect_experiment_ledger(protocol_path, root)
            self.assertEqual(ledger["status_counts"], {"completed": 1, "missing": 1})
            self.assertEqual(ledger["runs"][0]["metrics"]["metrics.score"], 1.0)
            self.assertEqual(len(ledger["runs"][0]["report_sha256"]), 64)

    def test_marks_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "report.json").write_text(
                json.dumps({"metrics": {"count": 1, "score": 0.5}}), encoding="utf-8"
            )
            protocol = {
                "schema_version": "vague_hydro.experiment_protocol.v1",
                "protocol_id": "test",
                "split": {},
                "claims": {},
                "runs": [
                    {
                        "run_id": "short",
                        "kind": "routing",
                        "role": "formal_method",
                        "expected_count": 2,
                        "report": "report.json",
                        "metric_paths": ["metrics.score"],
                    }
                ],
            }
            protocol_path = root / "protocol.json"
            protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
            ledger = collect_experiment_ledger(protocol_path, root)
            self.assertEqual(ledger["runs"][0]["status"], "count_mismatch")

    def test_reads_completed_count_from_expert_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "report.json").write_text(
                json.dumps({"completed_count": 3, "metrics": {"score": 0.5}}), encoding="utf-8"
            )
            protocol = {
                "schema_version": "vague_hydro.experiment_protocol.v1",
                "protocol_id": "test",
                "split": {},
                "claims": {},
                "runs": [
                    {
                        "run_id": "expert",
                        "kind": "expert_quality",
                        "role": "formal_method",
                        "expected_count": 3,
                        "report": "report.json",
                        "metric_paths": ["metrics.score"],
                    }
                ],
            }
            protocol_path = root / "protocol.json"
            protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
            ledger = collect_experiment_ledger(protocol_path, root)
            self.assertEqual(ledger["runs"][0]["observed_count"], 3)
            self.assertEqual(ledger["runs"][0]["status"], "completed")

    def test_preserves_failed_report_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "report.json").write_text(
                json.dumps({"status": "failed", "job_count": 2, "metrics": {"score": 0.0}}),
                encoding="utf-8",
            )
            protocol = {
                "schema_version": "vague_hydro.experiment_protocol.v1",
                "protocol_id": "test",
                "split": {},
                "claims": {},
                "runs": [
                    {
                        "run_id": "failed-service",
                        "kind": "service_reliability",
                        "role": "stress",
                        "expected_count": 2,
                        "report": "report.json",
                        "metric_paths": ["metrics.score"],
                    }
                ],
            }
            protocol_path = root / "protocol.json"
            protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
            ledger = collect_experiment_ledger(protocol_path, root)
            self.assertEqual(ledger["runs"][0]["observed_count"], 2)
            self.assertEqual(ledger["runs"][0]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
