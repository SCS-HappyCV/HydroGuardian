from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.schemas.tool_spec import load_tool_registry


DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "configs" / "tool_registry.yaml"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and summarize the HydroRemoteAgent tool registry.")
    parser.add_argument("--registry", type=str, default=str(DEFAULT_REGISTRY_PATH))
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    registry = load_tool_registry(args.registry)
    summary = {
        "schema_version": registry.schema_version,
        "num_tools": len(registry.tools),
        "tools": [
            {
                "name": tool.name,
                "version": tool.version,
                "capabilities": list(tool.capabilities),
                "required_modalities": list(tool.required_modalities),
                "result_types": list(tool.output.result_types),
                "deterministic": tool.deterministic,
                "verifier": tool.verifier,
            }
            for tool in registry.tools
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
