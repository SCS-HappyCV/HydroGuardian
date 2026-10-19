from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from hydro_remote_agent.runtime import build_mock_runtime, build_remote_runtime
from hydro_remote_agent.runtime.contracts import ExpertHealth, ExpertResult
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class RemoteExpertRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)

    def test_expert_health_round_trip(self) -> None:
        health = ExpertHealth(
            tool="geometry_relation_analysis",
            backend="geometry_numpy",
            status="ready",
            initialized=True,
            details={"operations": ["near"]},
        )
        self.assertEqual(ExpertHealth.from_dict(asdict(health)), health)

    def test_expert_result_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            local = build_mock_runtime(self.registry, temp_dir)
            local.prepare("point_semantic_segmentation")
            result = local.invoke(
                "point_semantic_segmentation",
                {"point_cloud_path": "tile.txt"},
                invocation_id="round_trip",
            )
            self.assertEqual(ExpertResult.from_dict(result.to_dict()), result)

    def test_remote_runtime_prepares_and_invokes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            local = build_mock_runtime(self.registry, Path(temp_dir) / "server")
            local.prepare("point_semantic_segmentation")
            server_result = local.invoke(
                "point_semantic_segmentation",
                {"point_cloud_path": "tile.txt"},
                invocation_id="remote_call",
            )
            responses = [
                _Response(
                    asdict(local.health_check("point_semantic_segmentation")[0])
                ),
                _Response(server_result.to_dict()),
            ]
            remote = build_remote_runtime(
                self.registry,
                "http://expert-worker:19090",
                Path(temp_dir) / "client",
            )
            with patch(
                "hydro_remote_agent.runtime.remote_adapter.urlopen",
                side_effect=responses,
            ) as mocked_urlopen:
                health = remote.prepare("point_semantic_segmentation")[0]
                result = remote.invoke(
                    "point_semantic_segmentation",
                    {"point_cloud_path": "tile.txt"},
                    invocation_id="remote_call",
                )

            self.assertEqual(health.status, "ready")
            self.assertEqual(result, server_result)
            self.assertEqual(mocked_urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
