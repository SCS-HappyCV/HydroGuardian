from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.runtime import build_mock_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.expert_api import create_expert_app


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"


class ExpertApiTest(unittest.TestCase):
    def test_prepare_and_invoke(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except (ImportError, RuntimeError):
            self.skipTest("fastapi is not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            registry = load_tool_registry(REGISTRY_PATH)
            runtime = build_mock_runtime(registry, temp_dir)
            with TestClient(create_expert_app(runtime)) as client:
                tools = client.get("/v1/tools")
                self.assertEqual(tools.status_code, 200)
                self.assertEqual(len(tools.json()["tools"]), 6)

                prepared = client.post(
                    "/v1/tools/point_semantic_segmentation/prepare",
                    json={},
                )
                self.assertEqual(prepared.status_code, 200)
                self.assertEqual(prepared.json()["status"], "ready")

                response = client.post(
                    "/v1/tools/point_semantic_segmentation/invoke",
                    json={
                        "invocation_id": "api_call",
                        "arguments": {"point_cloud_path": "tile.txt"},
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["invocation_id"], "api_call")


if __name__ == "__main__":
    unittest.main()
