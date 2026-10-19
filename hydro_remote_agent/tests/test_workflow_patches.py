from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.service.contracts import JobSubmission
from hydro_remote_agent.service.conversations import JobConversationStore
from hydro_remote_agent.service.store import JobStore
from hydro_remote_agent.service.worker import _merge_job_results
from hydro_remote_agent.service.workflow_patches import WorkflowPatchStore, infer_workflow_patch


class WorkflowPatchTest(unittest.TestCase):
    def test_infers_point_semantic_step_from_natural_language(self) -> None:
        patch = infer_workflow_patch(
            "再添加一个点云语义分割专家任务",
            {"assets": {"point_cloud_path": "artifact://cloud"}},
        )
        self.assertEqual(patch["tool"], "point_semantic_segmentation")
        self.assertEqual(patch["arguments"]["point_cloud_path"], "artifact://cloud")

    def test_rejects_patch_without_required_asset(self) -> None:
        with self.assertRaisesRegex(ValueError, "点云数据"):
            infer_workflow_patch("追加点云语义分割", {"assets": {}})

    def test_enqueues_step_on_same_job_and_preserves_job_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            plan = {
                "schema_version": "1.0", "request_id": "patch:1", "intent": "information",
                "action": {"type": "direct_answer", "answer": "done"},
                "expected_output": {"type": "text", "coordinate_space": "none"},
            }
            job = store.create_job(JobSubmission("patch:1", "query", {}, planned_request=plan))
            store.claim("execution", "worker")
            store.transition(job.job_id, "executing", "succeeded", result={"outcome": "response"})
            message = JobConversationStore(store).add(job.job_id, "user", "workflow_patch", "追加点云语义分割")
            previous_version = store.require(job.job_id).version
            patch = WorkflowPatchStore(store).enqueue(
                job.job_id, message["message_id"], "point_semantic_segmentation",
                {"point_cloud_path": "artifact://cloud", "return_probabilities": True},
            )
            updated = store.require(job.job_id)
            self.assertEqual(updated.job_id, job.job_id)
            self.assertEqual(updated.status, "queued_execution")
            self.assertGreater(updated.version, previous_version)
            step = store.step(patch["step_id"])
            self.assertEqual(step.status, "pending")
            self.assertEqual(step.phase, "workflow_patch_queued")

    def test_merges_new_batch_without_losing_previous_results(self) -> None:
        previous = {
            "outcome": "result",
            "terminal_artifacts": {"change_mask": "artifact://change"},
            "risk_candidates": [{"candidate_id": "risk-1"}],
            "workflow_result": {"steps": [{"step_id": "change"}], "terminal_artifacts": {"change_mask": "artifact://change"}},
        }
        current = {
            "outcome": "result",
            "terminal_artifacts": {"point_labels": "artifact://labels"},
            "risk_candidates": [],
            "workflow_result": {"steps": [{"step_id": "invoke"}], "terminal_artifacts": {"point_labels": "artifact://labels"}},
        }
        merged = _merge_job_results(previous, current)
        self.assertEqual(set(merged["terminal_artifacts"]), {"change_mask", "point_labels"})
        self.assertEqual([item["step_id"] for item in merged["workflow_result"]["steps"]], ["change", "invoke"])
        self.assertEqual(merged["risk_candidates"], [{"candidate_id": "risk-1"}])
        self.assertEqual(len(merged["execution_batches"]), 2)

    def test_patch_failure_preserves_error_recorded_by_expert_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            plan = {
                "schema_version": "1.0", "request_id": "patch:error", "intent": "information",
                "action": {"type": "direct_answer", "answer": "done"},
                "expected_output": {"type": "text", "coordinate_space": "none"},
            }
            job = store.create_job(JobSubmission("patch:error", "query", {}, planned_request=plan))
            store.claim("execution", "worker")
            store.transition(job.job_id, "executing", "succeeded", result={"outcome": "response"})
            conversation = JobConversationStore(store)
            message = conversation.add(job.job_id, "user", "workflow_patch", "追加点云语义分割")
            patches = WorkflowPatchStore(store)
            patch = patches.enqueue(
                job.job_id, message["message_id"], "point_semantic_segmentation",
                {"point_cloud_path": "artifact://cloud"},
            )
            patches.claim(job.job_id, "executor")
            expert_error = {
                "code": "expert_worker_failed",
                "message": "ModuleNotFoundError: No module named 'laspy'",
                "recoverable": False,
            }
            store.upsert_step(
                patch["step_id"], job.job_id, patch["tool"], status="failed",
                arguments=patch["arguments"], error=expert_error,
            )

            failed = patches.fail(
                patch["patch_id"],
                {"code": "workflow_failed", "message": "generic failure"},
            )

            self.assertEqual(failed["error"], expert_error)
            self.assertEqual(store.step(patch["step_id"]).error, expert_error)


if __name__ == "__main__":
    unittest.main()
