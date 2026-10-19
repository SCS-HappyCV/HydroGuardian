from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.service.contracts import JobSubmission
from hydro_remote_agent.service.store import JobStore
from hydro_remote_agent.service.workorders import WorkorderStore


class WorkorderStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = JobStore(Path(self.temp_dir.name) / "jobs.sqlite")
        submission = JobSubmission("request:workorder", "query", {
            "before_image_path": "artifact://before-image",
            "after_image_path": "artifact://after-image",
            "point_cloud_path": "artifact://scene-cloud",
        })
        job = self.store.create_job(submission)
        candidate = {
            "candidate_id": "candidate-1",
            "title": "岸线变化待核查",
            "summary": "检测到明显变化区域",
            "risk_type": "shoreline_change",
            "risk_level": "high",
            "score": 0.82,
            "rule_id": "change-area-v1",
            "recommendation": "安排现场核查",
            "evidence_refs": ["artifact://change-regions"],
            "quality_gate": {"status": "passed"},
        }
        self.store.transition(job.job_id, "queued_planning", "succeeded", result={"risk_candidates": [candidate]})
        self.job_id = job.job_id
        self.workorders = WorkorderStore(self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_full_workorder_closure_and_immutable_timeline(self) -> None:
        order = self.workorders.create_from_candidate({
            "job_id": self.job_id,
            "candidate_id": "candidate-1",
            "region_id": "region-1",
            "task_id": "task-1",
            "location": {
                "longitude": 109.6421395116,
                "latitude": 23.5799507319,
                "projected_x": 361381.6507,
                "projected_y": 2609423.1704,
                "epsg": 4546,
                "crs_name": "CGCS2000 / 3-degree Gauss-Kruger CM 111E",
                "geographic_bbox": {
                    "west": 109.6418595071,
                    "south": 23.5795488867,
                    "east": 109.6424447893,
                    "north": 23.5803075109,
                },
            },
        })
        self.assertEqual(order["status"], "todo")
        self.assertEqual(order["evidence"][0]["artifact_id"], "change-regions")
        self.assertEqual({item["artifact_id"] for item in order["evidence"]}, {
            "change-regions", "before-image", "after-image", "scene-cloud",
        })
        self.assertEqual(order["risk_snapshot"]["location"]["epsg"], 4546)
        self.assertAlmostEqual(order["risk_snapshot"]["location"]["longitude"], 109.6421395116)

        order = self.workorders.assign(order["workorder_id"], {"assignee_user_id": "inspector-1"})
        order = self.workorders.start(order["workorder_id"], {"actor_user_id": "inspector-1"})
        order = self.workorders.feedback(order["workorder_id"], {"actor_user_id": "inspector-1", "note": "现场已完成核查"})
        self.assertEqual(order["status"], "review")
        order = self.workorders.review(order["workorder_id"], {
            "reviewer_user_id": "reviewer-1", "decision": "approved", "comment": "证据充分，同意闭环",
        })
        self.assertEqual(order["status"], "closed")
        self.assertEqual([item["action"] for item in order["timeline"]], [
            "created", "assigned", "processing", "review_requested", "closed",
        ])
        self.assertEqual(order["reviews"][0]["decision"], "approved")

    def test_candidate_is_canonical_and_creation_is_idempotent(self) -> None:
        payload = {"job_id": self.job_id, "candidate_id": "candidate-1", "title": "伪造标题"}
        first = self.workorders.create_from_candidate(payload)
        second = self.workorders.create_from_candidate(payload)
        self.assertEqual(first["workorder_id"], second["workorder_id"])
        self.assertEqual(first["title"], "岸线变化待核查")

    def test_rejected_review_returns_to_processing(self) -> None:
        order = self.workorders.create_from_candidate({"job_id": self.job_id, "candidate_id": "candidate-1"})
        self.workorders.start(order["workorder_id"], {})
        self.workorders.feedback(order["workorder_id"], {"note": "已核查"})
        order = self.workorders.review(order["workorder_id"], {
            "decision": "rejected", "comment": "请补充现场照片",
        })
        self.assertEqual(order["status"], "doing")

    def test_unknown_candidate_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.workorders.create_from_candidate({"job_id": self.job_id, "candidate_id": "missing"})

    def test_feedback_is_idempotent_and_checks_version(self) -> None:
        order = self.workorders.create_from_candidate({"job_id": self.job_id, "candidate_id": "candidate-1"})
        order = self.workorders.start(order["workorder_id"], {})
        payload = {
            "note": "现场核查完成",
            "client_submission_id": "mobile-submit-1",
            "expected_version": order["version"],
        }
        first = self.workorders.feedback(order["workorder_id"], payload)
        second = self.workorders.feedback(order["workorder_id"], payload)
        self.assertEqual(first["version"], second["version"])
        self.assertEqual(len(first["timeline"]), len(second["timeline"]))
        self.assertEqual(len(first["evidence"]), len(second["evidence"]))

        other = self.workorders.create_from_candidate({
            "job_id": self.job_id,
            "candidate_id": "candidate-1",
            "region_id": "other-region",
        })
        with self.assertRaisesRegex(ValueError, "version conflict"):
            self.workorders.feedback(other["workorder_id"], {
                "note": "版本已过期",
                "expected_version": other["version"] + 1,
            })


if __name__ == "__main__":
    unittest.main()
