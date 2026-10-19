from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.api import create_app
from hydro_remote_agent.service.contracts import JobSubmission
from hydro_remote_agent.service.store import JobStore
from hydro_remote_agent.service.conversations import AgentChatQueue, JobConversationStore


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class JobConversationApiTest(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from fastapi.testclient import TestClient  # noqa: F401
        except (ImportError, RuntimeError):
            self.skipTest("fastapi test client is unavailable")

    def _app(self, database: Path):
        store = JobStore(database)
        registry = load_tool_registry(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
        return create_app(store, registry), store

    @staticmethod
    def _submission(request_id: str, task_id: str) -> dict:
        return {
            "request_id": request_id,
            "query": "检查近水区域变化",
            "assets": {"image_path": "artifact://art-image"},
            "task": {"task_id": task_id, "input_text": "检查近水区域变化", "scene_id": "scene-1"},
        }

    def test_status_question_and_context_are_persisted(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp_dir:
            app, _ = self._app(Path(temp_dir) / "jobs.sqlite")
            with TestClient(app) as client:
                job = client.post("/v1/jobs", json=self._submission("chat-1", "task-chat-1")).json()
                asked = client.post(
                    f"/v1/jobs/{job['job_id']}/messages",
                    headers={"Idempotency-Key": "message-status-1"},
                    json={"intent": "ask", "content": "现在执行到哪一步？"},
                )
                self.assertEqual(asked.status_code, 201)
                self.assertTrue(asked.json()["pending"])
                self.assertEqual(len(asked.json()["messages"]), 1)
                context = client.post(
                    f"/v1/jobs/{job['job_id']}/messages",
                    json={"intent": "append_context", "content": "重点检查距水线 20 米范围"},
                )
                self.assertEqual(context.status_code, 201)
                messages = client.get(f"/v1/jobs/{job['job_id']}/messages").json()["messages"]
                self.assertEqual([item["role"] for item in messages], ["user", "user"])
                self.assertEqual(messages[1]["intent"], "append_context")

    def test_message_intent_is_inferred_when_client_omits_selection(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp_dir:
            app, _ = self._app(Path(temp_dir) / "jobs.sqlite")
            with TestClient(app) as client:
                job = client.post("/v1/jobs", json=self._submission("chat-auto", "task-chat-auto")).json()
                asked = client.post(
                    f"/v1/jobs/{job['job_id']}/messages",
                    json={"content": "现在执行到哪一步了？"},
                ).json()
                self.assertEqual(asked["messages"][0]["intent"], "ask")
                self.assertEqual(
                    asked["messages"][0]["metadata"]["intent_classification"]["classified_by"],
                    "semantic_router_v1",
                )
                context = client.post(
                    f"/v1/jobs/{job['job_id']}/messages",
                    json={"content": "重点检查距水线 20 米范围并排除道路"},
                ).json()
                self.assertEqual(context["messages"][0]["intent"], "append_context")

    def test_replan_requires_confirmation_and_creates_successor(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp_dir:
            app, store = self._app(Path(temp_dir) / "jobs.sqlite")
            with TestClient(app) as client:
                job = client.post("/v1/jobs", json=self._submission("chat-2", "task-chat-2")).json()
                client.post(
                    f"/v1/jobs/{job['job_id']}/messages",
                    json={"intent": "append_context", "content": "排除道路区域"},
                )
                rejected = client.post(
                    f"/v1/jobs/{job['job_id']}/interventions",
                    json={"action": "replan", "content": "改用变化检测"},
                )
                self.assertEqual(rejected.status_code, 409)
                replanned = client.post(
                    f"/v1/jobs/{job['job_id']}/interventions",
                    headers={"Idempotency-Key": "replan-1"},
                    json={"action": "replan", "content": "改用变化检测", "confirmed": True},
                )
                self.assertEqual(replanned.status_code, 202)
                payload = replanned.json()
                self.assertEqual(store.require(job["job_id"]).status, "cancelled")
                self.assertNotEqual(payload["job"]["job_id"], job["job_id"])
                self.assertIn("排除道路区域", payload["job"]["submission"]["query"])
                self.assertIn("改用变化检测", payload["job"]["submission"]["query"])
                task = client.get("/v1/tasks/task-chat-2").json()
                self.assertEqual(task["job_id"], payload["job"]["job_id"])
                self.assertEqual(task["metadata"]["parent_job_id"], job["job_id"])

    def test_workflow_patch_adds_step_without_creating_successor_job(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp_dir:
            app, store = self._app(Path(temp_dir) / "jobs.sqlite")
            with TestClient(app) as client:
                job = client.post("/v1/jobs", json={
                    **self._submission("chat-patch", "task-chat-patch"),
                    "assets": {"point_cloud_path": "artifact://cloud"},
                    "planned_request": {
                        "schema_version": "1.0", "request_id": "chat-patch", "intent": "information",
                        "action": {"type": "direct_answer", "answer": "ready"},
                        "expected_output": {"type": "text", "coordinate_space": "none"},
                    },
                }).json()
                response = client.post(
                    f"/v1/jobs/{job['job_id']}/messages",
                    json={"content": "再添加点云语义分割任务"},
                )
                self.assertEqual(response.status_code, 201)
                payload = response.json()
                self.assertFalse(payload["pending"])
                self.assertEqual(payload["job_id"], job["job_id"])
                self.assertEqual(payload["workflow_patch"]["tool"], "point_semantic_segmentation")
                self.assertEqual(len(store.list_jobs()), 1)
                self.assertEqual(store.steps(job["job_id"])[0].status, "pending")


class AgentChatQueueTest(unittest.TestCase):
    def test_queue_is_idempotent_and_recovers_expired_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            store.create_job(JobSubmission.from_dict({
                "request_id": "chat-queue-1", "query": "检查状态", "assets": {},
            }))
            job = store.list_jobs()[0]
            messages = JobConversationStore(store)
            message = messages.add(job.job_id, "user", "ask", "当前状态？")
            queue = AgentChatQueue(store)
            first = queue.enqueue(job.job_id, message["message_id"])
            duplicate = queue.enqueue(job.job_id, message["message_id"])
            self.assertEqual(first["request_id"], duplicate["request_id"])
            claimed = queue.claim("planner-1", lease_seconds=1)
            self.assertEqual(claimed["status"], "running")
            with store._session() as connection:
                connection.execute(
                    "UPDATE agent_chat_requests SET lease_expires_at=0 WHERE request_id=?",
                    (claimed["request_id"],),
                )
            recovered = queue.claim("planner-2", lease_seconds=60)
            self.assertEqual(recovered["request_id"], claimed["request_id"])
            self.assertEqual(recovered["attempts"], 2)
            self.assertEqual(queue.complete(recovered["request_id"])["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
