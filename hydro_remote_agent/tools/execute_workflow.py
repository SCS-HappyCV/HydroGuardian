from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.runtime import load_expert_runtime
from hydro_remote_agent.schemas.agent_action import load_agent_request
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.workflow import WorkflowExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"
DEFAULT_RUNTIME_PATH = PACKAGE_ROOT / "configs" / "expert_runtime.yaml"
DEFAULT_WORKFLOW_DIR = PACKAGE_ROOT / "runs" / "workflows"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute a validated HydroRemoteAgent workflow.")
    parser.add_argument("action", help="Path to an Agent action JSON file.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--runtime", default=str(DEFAULT_RUNTIME_PATH))
    parser.add_argument("--expert-work-dir", default=None)
    parser.add_argument("--workflow-work-dir", default=str(DEFAULT_WORKFLOW_DIR))
    parser.add_argument("--execution-id", default=None)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    registry = load_tool_registry(args.registry)
    request = load_agent_request(args.action, registry)
    runtime = load_expert_runtime(args.runtime, registry, work_dir=args.expert_work_dir)
    try:
        executor = WorkflowExecutor(runtime, args.workflow_work_dir)
        result = executor.execute(request, execution_id=args.execution_id)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    main()
