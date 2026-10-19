from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.api import create_app
from hydro_remote_agent.service.store import JobStore
from hydro_remote_agent.service.websocket_hub import WorkerHub


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class RemotePlannerApiTest(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from fastapi.testclient import TestClient  # noqa: F401
        except (ImportError, RuntimeError):
            self.skipTest("fastapi test client is unavailable")

    def _app(self, database: Path):
        store = JobStore(database)
        registry = load_tool_registry(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
        hub = WorkerHub(worker_secret="planner-secret", store=store)
        return create_app(store, registry, worker_hub=hub), store

    def test_remote_planner_claim_and_complete(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp_dir:
            app, store = self._app(Path(temp_dir) / "jobs.sqlite")
            with TestClient(app) as client:
                created = client.post("/v1/jobs", json={
                    "request_id": "planner-api-1",
                    "query": "请分析当前资料",
                    "assets": {},
                })
                self.assertEqual(created.status_code, 202)
                job_id = created.json()["job_id"]
                headers = {"X-Worker-Secret": "planner-secret", "X-Worker-Id": "planner-gpu-0"}
                claimed = client.post("/internal/planner/claim", headers=headers)
                self.assertEqual(claimed.status_code, 200)
                self.assertEqual(claimed.json()["job"]["job_id"], job_id)
                completed = client.post(
                    f"/internal/planner/{job_id}/complete",
                    headers=headers,
                    json={"plan": {
                        "schema_version": "1.0",
                        "request_id": "planner-api-1",
                        "intent": "information",
                        "action": {"type": "direct_answer", "answer": "资料已接收。"},
                        "expected_output": {"type": "text", "coordinate_space": "none"},
                    }},
                )
                self.assertEqual(completed.status_code, 200)
                self.assertEqual(completed.json()["status"], "queued_execution")
                self.assertEqual(store.require(job_id).lease_owner, None)
                self.assertEqual(store.events(job_id)[-1]["event_type"], "planning_succeeded")

    def test_remote_planner_rejects_invalid_secret(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp_dir:
            app, _ = self._app(Path(temp_dir) / "jobs.sqlite")
            with TestClient(app) as client:
                response = client.post(
                    "/internal/planner/claim",
                    headers={"X-Worker-Secret": "wrong-secret"},
                )
                self.assertEqual(response.status_code, 401)

    def test_remote_planner_chat_claim_and_complete(self) -> None:
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temp_dir:
            app, _ = self._app(Path(temp_dir) / "jobs.sqlite")
            with TestClient(app) as client:
                job = client.post("/v1/jobs", json={
                    "request_id": "planner-chat-1", "query": "检查近水区", "assets": {},
                }).json()
                sent = client.post(
                    f"/v1/jobs/{job['job_id']}/messages", json={"content": "当前有哪些专家在执行？"},
                ).json()
                headers = {"X-Worker-Secret": "planner-secret", "X-Worker-Id": "planner-gpu-0"}
                claimed = client.post("/internal/planner/chat/claim", headers=headers).json()["request"]
                self.assertEqual(claimed["request"]["request_id"], sent["chat_request_id"])
                self.assertEqual(claimed["messages"][-1]["content"], "当前有哪些专家在执行？")
                completed = client.post(
                    f"/internal/planner/chat/{sent['chat_request_id']}/complete",
                    headers=headers, json={"answer": "任务仍在等待规划，尚未调度专家。", "metadata": {"tokens": 18}},
                )
                self.assertEqual(completed.status_code, 200)
                message = completed.json()["message"]
                self.assertEqual(message["metadata"]["generated_by"], "qwen3_vl_planner")
                self.assertEqual(message["metadata"]["reply_to"], sent["messages"][0]["message_id"])


if __name__ == "__main__":
    unittest.main()
