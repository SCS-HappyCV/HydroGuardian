from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.runtime import load_expert_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"
DEFAULT_RUNTIME_PATH = PACKAGE_ROOT / "configs" / "expert_runtime.yaml"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operate HydroRemoteAgent expert adapters.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--runtime", default=str(DEFAULT_RUNTIME_PATH))
    parser.add_argument("--work-dir", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    health_parser = subparsers.add_parser("health", help="Prepare and inspect expert health.")
    health_parser.add_argument("--tool", default=None)

    invoke_parser = subparsers.add_parser("invoke", help="Invoke one configured expert.")
    invoke_parser.add_argument("--tool", required=True)
    invoke_parser.add_argument("--arguments", required=True, help="JSON object with tool arguments.")
    invoke_parser.add_argument("--invocation-id", default=None)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    registry = load_tool_registry(args.registry)
    runtime = load_expert_runtime(args.runtime, registry, work_dir=args.work_dir)
    try:
        if args.command == "health":
            health = runtime.prepare(args.tool)
            print(json.dumps([asdict(item) for item in health], ensure_ascii=False, indent=2))
            return
        arguments = json.loads(args.arguments)
        if not isinstance(arguments, dict):
            raise ValueError("--arguments must decode to a JSON object")
        runtime.prepare(args.tool)
        result = runtime.invoke(args.tool, arguments, invocation_id=args.invocation_id)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    main()
