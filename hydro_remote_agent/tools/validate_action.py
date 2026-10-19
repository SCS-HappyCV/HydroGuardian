from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.schemas.agent_action import load_agent_request
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an Agent action against the HydroRemoteAgent tool registry."
    )
    parser.add_argument("action", type=str, help="Path to an Agent action JSON file.")
    parser.add_argument("--registry", type=str, default=str(DEFAULT_REGISTRY_PATH))
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    registry = load_tool_registry(args.registry)
    request = load_agent_request(args.action, registry)
    print(json.dumps(asdict(request), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
