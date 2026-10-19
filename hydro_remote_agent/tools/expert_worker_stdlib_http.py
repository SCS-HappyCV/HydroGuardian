from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from urllib.parse import unquote, urlparse

from hydro_remote_agent.runtime import load_expert_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dependency-free local Expert Worker HTTP API.")
    parser.add_argument("--registry", default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml"))
    parser.add_argument("--runtime", default=str(PACKAGE_ROOT / "configs" / "expert_runtime.yaml"))
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19091)
    return parser


def _handler(runtime):
    class ExpertHandler(BaseHTTPRequestHandler):
        server_version = "VagueHydroExpert/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            print(f"EXPERT_HTTP {self.address_string()} {format % args}", flush=True)

        def _send(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                raise ValueError("request body must be an object")
            return payload

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/healthz":
                experts = [asdict(item) for item in runtime.health_check()]
                self._send(200, {"status": "ok", "experts": experts, "unavailable": []})
                return
            if path == "/v1/tools":
                self._send(200, {"tools": [
                    {
                        "name": tool.name,
                        "version": tool.version,
                        "backend": runtime.get_adapter(tool.name).backend,
                    }
                    for tool in runtime.registry.tools
                ]})
                return
            self._send(404, {"detail": "not found"})

        def do_POST(self) -> None:
            parts = [unquote(part) for part in urlparse(self.path).path.split("/") if part]
            if len(parts) != 4 or parts[:2] != ["v1", "tools"]:
                self._send(404, {"detail": "not found"})
                return
            tool_name, operation = parts[2], parts[3]
            try:
                payload = self._read_json()
                if operation == "prepare":
                    self._send(200, asdict(runtime.prepare(tool_name)[0]))
                    return
                if operation == "invoke":
                    arguments = payload.get("arguments")
                    if not isinstance(arguments, dict):
                        raise ValueError("arguments must be an object")
                    invocation_id = payload.get("invocation_id")
                    result = runtime.invoke(tool_name, arguments, invocation_id)
                    self._send(200, result.to_dict())
                    return
                self._send(404, {"detail": "unknown operation"})
            except (KeyError, ValueError, TypeError) as exc:
                self._send(422, {"detail": f"{type(exc).__name__}: {exc}"})
            except Exception as exc:
                self._send(500, {"detail": f"{type(exc).__name__}: {exc}"})

    return ExpertHandler


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    registry = load_tool_registry(args.registry)
    runtime = load_expert_runtime(args.runtime, registry, work_dir=args.work_dir)
    server = ThreadingHTTPServer((args.host, args.port), _handler(runtime))
    print(f"EXPERT_STDLIB_HTTP_READY host={args.host} port={args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        runtime.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
