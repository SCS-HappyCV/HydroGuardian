from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from hydro_remote_agent.runtime import build_mock_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.api import create_app
from hydro_remote_agent.service.contracts import JobSubmission
from hydro_remote_agent.service.store import JobStore
from hydro_remote_agent.service.infra import NullEventBus, event_payload


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class SseAndInfraTest(unittest.TestCase):
    def test_event_payload_and_null_bus(self) -> None:
        payload = event_payload("job-1", {"event_id": 3, "event_type": "created"})
        self.assertEqual(payload["job_id"], "job-1")
        NullEventBus().publish(payload)

    def test_api_publishes_creation_and_exposes_stream(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except (ImportError, RuntimeError):
            self.skipTest("fastapi is not installed")
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            registry = load_tool_registry(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
            bus = Mock()
            app = create_app(store, registry, event_bus=bus)
            with TestClient(app) as client:
                response = client.post("/v1/jobs", json={
                    "request_id": "sse-1", "query": "test", "assets": {},
                    "planned_request": {
                        "schema_version": "1.0", "request_id": "sse-1", "intent": "information",
                        "action": {"type": "direct_answer", "answer": "ok"},
                        "expected_output": {"type": "text", "coordinate_space": "none"},
                    },
                })
                self.assertEqual(response.status_code, 202)
                self.assertTrue(bus.publish.called)
                job_id = response.json()["job_id"]
                with client.stream("GET", f"/v1/jobs/{job_id}/events/stream") as stream:
                    body = "".join(stream.iter_text())
                self.assertIn("event: job", body)
                self.assertIn("created", body)


if __name__ == "__main__":
    unittest.main()
