from __future__ import annotations

import json
from pathlib import Path

from hydro_remote_agent.runtime.agent_service_executor import AgentServiceExecutionClient
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


class FakeServiceClient(AgentServiceExecutionClient):
    def __init__(self, work_dir: Path) -> None:
        super().__init__("http://service.invalid", work_dir, poll_seconds=0.05)
        self.calls: list[tuple[str, str, object, object]] = []

    def _json_request(self, method, path, payload=None, headers=None):
        self.calls.append((method, path, payload, headers))
        if method == "POST":
            return {"job_id": "job_test", "status": "queued_execution"}
        return {
            "job_id": "job_test",
            "status": "succeeded",
            "result": {
                "status": "succeeded",
                "execution_mode": "planner_only",
                "terminal_artifacts": {},
            },
        }


def test_agent_service_client_executes_frozen_direct_request(tmp_path: Path) -> None:
    request_id = "q:test:direct"
    prediction = {
        "schema_version": "1.0",
        "request_id": request_id,
        "intent": "attribute_judgement",
        "action": {"type": "direct_answer", "answer": "Yes."},
        "expected_output": {"type": "text", "coordinate_space": "none"},
    }
    record = {
        "id": request_id,
        "language": "en",
        "messages": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request_id": request_id,
                        "query": "Is the target present?",
                        "language": "en",
                        "assets": {"image_path": "/data/image.png"},
                    }
                ),
            }
        ],
    }
    registry = load_tool_registry(
        Path(__file__).resolve().parents[1] / "configs" / "tool_registry.yaml"
    )
    client = FakeServiceClient(tmp_path)
    execution, parsed, elapsed_ms = client.execute_prediction(
        json.dumps(prediction),
        request_id,
        "test",
        record,
        registry,
    )
    assert execution["status"] == "succeeded"
    assert execution["service_job_id"] == "job_test"
    assert parsed == prediction
    assert elapsed_ms >= 0.0
    assert client.calls[0][0:2] == ("POST", "/v1/jobs")
    assert client.calls[0][2]["planned_request"] == prediction
    assert client.calls[0][2]["assets"] == {}


def test_agent_service_client_uses_configured_idempotency_namespace(
    tmp_path: Path,
) -> None:
    client = FakeServiceClient(tmp_path)
    client.idempotency_namespace = "formal-rerun"
    prediction = {
        "schema_version": "1.0",
        "request_id": "q:test:namespace",
        "intent": "attribute_judgement",
        "action": {"type": "direct_answer", "answer": "Yes."},
        "expected_output": {"type": "text", "coordinate_space": "none"},
    }
    record = {
        "id": "q:test:namespace",
        "messages": [
            {
                "role": "user",
                "content": json.dumps({"query": "Present?", "assets": {}}),
            }
        ],
    }
    registry = load_tool_registry(
        Path(__file__).resolve().parents[1] / "configs" / "tool_registry.yaml"
    )
    client.execute_prediction(
        json.dumps(prediction),
        "q:test:namespace",
        "glm_final",
        record,
        registry,
    )
    assert client.calls[0][0:2] == ("POST", "/v1/jobs")
    assert client.calls[0][3]["Idempotency-Key"] == (
        "formal-rerun:glm_final:q:test:namespace"
    )


def test_artifact_proxy_preserves_signed_host_and_query(tmp_path: Path) -> None:
    client = AgentServiceExecutionClient(
        "http://service.invalid",
        tmp_path,
        artifact_proxy_url="http://127.0.0.1:29000",
    )
    request = client._artifact_download_request(
        "http://172.16.224.4:19000/bucket/a.npz?X-Amz-Signature=abc"
    )
    assert request.full_url == (
        "http://127.0.0.1:29000/bucket/a.npz?X-Amz-Signature=abc"
    )
    assert request.get_header("Host") == "172.16.224.4:19000"
