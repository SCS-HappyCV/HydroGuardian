from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.runtime import load_expert_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.expert_api import create_expert_app


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the VagueHydro Expert Worker HTTP API.")
    parser.add_argument(
        "--registry", default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
    )
    parser.add_argument(
        "--runtime", default=str(PACKAGE_ROOT / "configs" / "expert_runtime.yaml")
    )
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=19090)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Expert Worker API requires uvicorn") from exc
    registry = load_tool_registry(args.registry)
    runtime = load_expert_runtime(args.runtime, registry, work_dir=args.work_dir)
    uvicorn.run(create_expert_app(runtime), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
