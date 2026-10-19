from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.service.contracts import JobSubmission
from hydro_remote_agent.service.store import JobStore
from hydro_remote_agent.service.task_history import TaskHistoryStore
from hydro_remote_agent.service.workorders import WorkorderStore


class TaskHistoryStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.jobs = JobStore(Path(self.temp_dir.name) / "jobs.sqlite")
        self.workorders = WorkorderStore(self.jobs)
        self.tasks = TaskHistoryStore(self.jobs)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_task_metadata_and_job_state_are_aggregated(self) -> None:
        job = self.jobs.create_job(JobSubmission("request:task", "检测岸线变化", {}, planned_request={"request_id": "request:task"}))
        task = self.tasks.upsert(job.job_id, {
            "task_id": "task-live-1", "name": "岸线变化巡查", "input_text": "检测岸线变化",
            "zone_id": "zone-01", "scene_id": "scene-01", "priority": "high",
        })
        self.assertEqual(task["status"], "queued")
        self.assertEqual(task["progress"], 25)
        self.assertEqual(task["job_id"], job.job_id)

        self.jobs.claim("execution", "worker-1")
        self.jobs.upsert_step("step-1", job.job_id, "image_change_detection", status="running", progress=0.6)
        task = self.tasks.require("task-live-1")
        self.assertEqual(task["status"], "running")
        self.assertEqual(task["progress"], 60)
        self.assertEqual(task["step_count"], 1)

    def test_completed_task_exposes_risk_and_history_counts(self) -> None:
        job = self.jobs.create_job(JobSubmission("request:done", "检测风险", {}))
        self.tasks.upsert(job.job_id, {"task_id": "task-done", "input_text": "检测风险"})
        self.jobs.transition(job.job_id, "queued_planning", "succeeded", result={
            "risk_candidates": [{"candidate_id": "risk-1"}],
            "terminal_artifacts": {"report": "artifact://report"},
        })
        task = self.tasks.require("task-done")
        self.assertEqual(task["status"], "success")
        self.assertEqual(task["risk_count"], 1)
        self.assertEqual(task["artifact_count"], 1)
        history = self.tasks.history("task-done")
        self.assertEqual(history["job"]["status"], "succeeded")

    def test_filters_and_upsert(self) -> None:
        first = self.jobs.create_job(JobSubmission("request:1", "北岸巡查", {}))
        second = self.jobs.create_job(JobSubmission("request:2", "南岸巡查", {}))
        self.tasks.upsert(first.job_id, {"task_id": "north", "input_text": "北岸巡查", "zone_id": "north-zone"})
        self.tasks.upsert(second.job_id, {"task_id": "south", "input_text": "南岸巡查", "zone_id": "south-zone"})
        self.tasks.upsert(first.job_id, {"task_id": "north", "name": "北岸重点巡查", "input_text": "北岸巡查", "zone_id": "north-zone"})
        self.assertEqual(self.tasks.require("north")["name"], "北岸重点巡查")
        self.assertEqual([item["task_id"] for item in self.tasks.list(zone_id="south-zone")], ["south"])
        self.assertEqual([item["task_id"] for item in self.tasks.list(keyword="重点")], ["north"])


if __name__ == "__main__":
    unittest.main()
