from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.api import create_app
from hydro_remote_agent.service.store import JobStore
from hydro_remote_agent.service.websocket_protocol import make_message


class WebSocketHttpHandshakeTest(unittest.TestCase):
    def setUp(self) -> None:
        try:
            import fastapi  # noqa: F401
        except ImportError:
            self.skipTest("fastapi is unavailable")

    def _create_app(self, database: Path):
        root = Path(__file__).resolve().parents[1]
        return create_app(
            JobStore(database),
            load_tool_registry(root / "configs" / "tool_registry.yaml"),
        )

    def test_fastapi_identifies_websocket_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._create_app(Path(temp_dir) / "jobs.sqlite")
            route = next(route for route in app.routes if route.path == "/internal/workers/ws")
            self.assertEqual(route.dependant.websocket_param_name, "websocket")

    def test_fastapi_accepts_worker_registration(self) -> None:
        try:
            from fastapi.testclient import TestClient
        except (ImportError, RuntimeError):
            self.skipTest("fastapi test client is unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._create_app(Path(temp_dir) / "jobs.sqlite")
            with TestClient(app) as client:
                with client.websocket_connect("/internal/workers/ws") as socket:
                    socket.send_json(make_message(
                        "register", worker_id="handshake-worker",
                        capabilities=["geometry_relation_analysis"], gpus=[],
                    ))
                    self.assertEqual(socket.receive_json()["type"], "registered")


if __name__ == "__main__":
    unittest.main()
