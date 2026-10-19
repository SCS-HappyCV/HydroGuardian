from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.schemas.tool_spec import ToolRegistry
from hydro_remote_agent.service.api import create_app
from hydro_remote_agent.service.contracts import JobSubmission
from hydro_remote_agent.service.store import JobStore


class AuditReportApiTest(unittest.TestCase):
    def test_report_contains_execution_workorders_and_verifiable_digest(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except ImportError as exc:
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            job = store.create_job(JobSubmission(
                "request:audit",
                "核查岸线变化",
                {"after_image_path": "artifact://after-image"},
            ))
            store.transition(job.job_id, "queued_planning", "succeeded", result={
                "risk_candidates": [{
                    "candidate_id": "candidate-1",
                    "title": "岸线变化待核查",
                    "risk_type": "shoreline_change",
                    "risk_level": "high",
                    "score": 0.82,
                    "evidence_refs": ["artifact://change-mask"],
                }],
                "spatial_context": {"schema_version": "hydro-spatial-context.v1"},
            })
            app = create_app(store, ToolRegistry())
            with TestClient(app) as client:
                order = client.post("/v1/workorders", json={
                    "job_id": job.job_id,
                    "candidate_id": "candidate-1",
                    "region_id": "region-1",
                })
                self.assertEqual(order.status_code, 201)
                response = client.get(f"/v1/reports/jobs/{job.job_id}")
            self.assertEqual(response.status_code, 200)
            report = response.json()
            integrity = report.pop("integrity")
            def normalize(value):
                if isinstance(value, bool) or value is None or isinstance(value, str):
                    return value
                if isinstance(value, int):
                    return str(value)
                if isinstance(value, float):
                    if value.is_integer():
                        return str(int(value))
                    return f"{value:.15f}".rstrip("0").rstrip(".")
                if isinstance(value, dict):
                    return {key: normalize(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [normalize(item) for item in value]
                return str(value)

            canonical = json.dumps(normalize(report), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            self.assertEqual(integrity["digest"], hashlib.sha256(canonical.encode("utf-8")).hexdigest())
            self.assertEqual(report["subject"]["job_id"], job.job_id)
            self.assertEqual(len(report["workorders"]), 1)
            self.assertEqual({item["artifact_id"] for item in report["artifacts"]}, {"after-image", "change-mask"})


if __name__ == "__main__":
    unittest.main()
