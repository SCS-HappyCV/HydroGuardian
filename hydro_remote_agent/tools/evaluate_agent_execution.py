from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.evaluation.execution import execute_predictions, summarize_execution
from hydro_remote_agent.runtime import load_expert_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.workflow import AgentExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute Planner predictions through real expert adapters."
    )
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument(
        "--registry", default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
    )
    parser.add_argument(
        "--runtime", default=str(PACKAGE_ROOT / "configs" / "expert_runtime.yaml")
    )
    parser.add_argument("--expert-work-dir", required=True)
    parser.add_argument("--execution-work-dir", required=True)
    parser.add_argument("--max-expert-executions", type=int)
    parser.add_argument("--allow-mock", action="store_true")
    parser.add_argument("--max-error-examples", type=int, default=20)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_expert_executions is not None and args.max_expert_executions < 0:
        raise ValueError("--max-expert-executions must be non-negative")
    registry = load_tool_registry(args.registry)
    runtime = load_expert_runtime(
        args.runtime,
        registry,
        work_dir=args.expert_work_dir,
    )
    output_path = Path(args.output)
    try:
        stats = execute_predictions(
            prediction_path=Path(args.predictions),
            output_path=output_path,
            executor=AgentExecutor(runtime, args.execution_work_dir),
            registry=registry,
            max_expert_executions=args.max_expert_executions,
            skip_mock=not args.allow_mock,
        )
    finally:
        runtime.shutdown()
    report = summarize_execution(
        prediction_path=Path(args.predictions),
        output_path=output_path,
        run_stats=stats,
        max_error_examples=max(args.max_error_examples, 0),
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        "VAGUE_HYDRO_EXECUTION_EVAL_OK "
        f"status={report['status']} completed={report['completed_count']} "
        f"real={report['real_expert_succeeded_count']}/"
        f"{report['real_expert_attempted_count']} mock_skipped={report['mock_skipped_count']} "
        f"report={report_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
