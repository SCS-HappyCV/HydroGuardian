from __future__ import annotations

import argparse
import copy
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json, read_jsonl
from hydro_remote_agent.baselines.rule_router import RuleRouter
from hydro_remote_agent.evaluation.routing import sha256_file
from hydro_remote_agent.runtime import build_remote_runtime, load_expert_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.run_agent_e2e_condition import (
    _completed_ids,
    _execute_prediction,
    _invocation_count,
)
from hydro_remote_agent.workflow import AgentExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONDITION = "rule_router"


def _execution_compatible_request(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Map the frozen multimodal alias to its current shared GUFNet ToolSpec."""
    compatible = copy.deepcopy(dict(request))
    action = compatible.get("action", {})
    actions = action.get("steps", []) if action.get("type") == "workflow" else [action]
    for step in actions:
        if step.get("tool") != "multimodal_semantic_segmentation":
            continue
        step["tool"] = "point_semantic_segmentation"
        arguments = step.get("arguments", {})
        arguments.pop("image_path", None)
    return compatible


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute deterministic RuleRouter requests through the real Agent runtime."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-input-sha256")
    parser.add_argument(
        "--registry", default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
    )
    parser.add_argument(
        "--runtime", default=str(PACKAGE_ROOT / "configs" / "expert_runtime.yaml")
    )
    parser.add_argument("--expert-base-url")
    parser.add_argument("--agent-service-url")
    parser.add_argument("--agent-artifact-proxy-url")
    parser.add_argument("--service-idempotency-namespace", default="hydro-agent-bench-gate")
    parser.add_argument("--expert-timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--service-poll-seconds", type=float, default=0.5)
    parser.add_argument("--expert-work-dir", required=True)
    parser.add_argument("--execution-work-dir", required=True)
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--resume", action="store_true")
    return parser


def rule_run_record(
    record: Mapping[str, Any],
    router: RuleRouter,
    executor: AgentExecutor,
    registry,
) -> Dict[str, Any]:
    request_id = str(record["id"])
    total_started = time.perf_counter()
    plan = router.plan(record)
    prediction = canonical_json(plan.request)
    execution_request = _execution_compatible_request(plan.request)
    execution_prediction = canonical_json(execution_request)
    planner_ms = float(plan.trace.get("latency_seconds", 0.0)) * 1000.0
    execution, parsed_request, execution_ms = _execute_prediction(
        execution_prediction,
        request_id,
        f"{CONDITION}_final",
        executor,
        registry,
        record,
    )
    return {
        "id": request_id,
        "condition": CONDITION,
        "prediction": prediction,
        "execution": execution,
        "expert_invocation_count": _invocation_count(execution),
        "timing": {
            "planner_ms": planner_ms,
            "execution_ms": execution_ms,
            "total_ms": (time.perf_counter() - total_started) * 1000.0,
            "model_load_excluded": True,
        },
        "generated_tokens": 0,
        "trace": [
            {
                "round": 0,
                "source": "deterministic_rule_router",
                "prediction": prediction,
                "execution_prediction": execution_prediction,
                "compatibility_mapping": (
                    "multimodal_semantic_segmentation_to_point_semantic_segmentation"
                    if prediction != execution_prediction
                    else None
                ),
                "parsed_request": parsed_request,
                "router_trace": plan.trace,
                "generated_tokens": 0,
                "planner_ms": planner_ms,
            }
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = Path(args.input)
    input_sha256 = sha256_file(input_path)
    if args.expected_input_sha256 and input_sha256 != args.expected_input_sha256:
        raise ValueError(
            f"Frozen input SHA256 mismatch: expected {args.expected_input_sha256}, "
            f"got {input_sha256}"
        )
    registry = load_tool_registry(args.registry)
    if args.agent_service_url and args.expert_base_url:
        raise ValueError("Use only one of --agent-service-url and --expert-base-url")
    runtime = None
    if args.agent_service_url:
        from hydro_remote_agent.runtime.agent_service_executor import (
            AgentServiceExecutionClient,
        )

        executor = AgentServiceExecutionClient(
            base_url=args.agent_service_url,
            work_dir=args.execution_work_dir,
            timeout_seconds=args.expert_timeout_seconds,
            poll_seconds=args.service_poll_seconds,
            artifact_proxy_url=args.agent_artifact_proxy_url,
            idempotency_namespace=args.service_idempotency_namespace,
        )
    else:
        runtime = (
            build_remote_runtime(
                registry,
                base_url=args.expert_base_url,
                work_dir=args.expert_work_dir,
                timeout_seconds=args.expert_timeout_seconds,
            )
            if args.expert_base_url
            else load_expert_runtime(args.runtime, registry, work_dir=args.expert_work_dir)
        )
        executor = AgentExecutor(runtime, args.execution_work_dir)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = _completed_ids(output) if args.resume else set()
    mode = "a" if args.resume and output.exists() else "w"
    router = RuleRouter()
    try:
        records = read_jsonl(input_path)
        if args.max_records is not None:
            if args.max_records < 0:
                raise ValueError("--max-records must be non-negative")
            records = records[: args.max_records]
        with output.open(mode, encoding="utf-8", newline="\n") as handle:
            for index, record in enumerate(records, start=1):
                if str(record["id"]) in completed:
                    continue
                row = rule_run_record(record, router, executor, registry)
                handle.write(canonical_json(row) + "\n")
                handle.flush()
                print(
                    f"RULE_E2E_REQUEST_OK index={index} id={row['id']} "
                    f"status={row['execution']['status']} "
                    f"total_ms={row['timing']['total_ms']:.1f}",
                    flush=True,
                )
    finally:
        if runtime is not None:
            runtime.shutdown()
        else:
            executor.shutdown()
    print(f"RULE_E2E_CONDITION_OK input_sha256={input_sha256} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
