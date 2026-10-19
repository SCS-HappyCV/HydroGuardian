from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json, read_jsonl
from hydro_remote_agent.evaluation.routing import extract_gold, sha256_file
from hydro_remote_agent.runtime import (
    build_remote_runtime,
    load_expert_runtime,
    overlay_remote_tools,
)
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tool_aliases import (
    execution_request_with_aliases as _execution_request_with_aliases,
    parse_tool_aliases as _parse_tool_aliases,
)
from hydro_remote_agent.tools.run_agent_e2e_condition import (
    _completed_ids,
    _execute_prediction,
    _invocation_count,
)
from hydro_remote_agent.workflow import AgentExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONDITION = "oracle_gold_routing"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute frozen gold AgentRequests to measure the expert-system upper bound."
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
    parser.add_argument(
        "--tool-base-url",
        action="append",
        default=[],
        metavar="TOOL=URL",
        help="Route one tool to an independent Expert Worker; repeat for multiple tools.",
    )
    parser.add_argument("--agent-service-url")
    parser.add_argument("--agent-artifact-proxy-url")
    parser.add_argument("--service-idempotency-namespace", default="task-aware-240")
    parser.add_argument("--expert-timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--service-poll-seconds", type=float, default=0.5)
    parser.add_argument("--expert-work-dir", required=True)
    parser.add_argument("--execution-work-dir", required=True)
    parser.add_argument("--max-records", type=int)
    parser.add_argument(
        "--action-type",
        action="append",
        choices=("direct_answer", "tool_call", "workflow", "clarification", "abstain"),
        help="Execute only gold requests with this action type; repeat for multiple types.",
    )
    parser.add_argument(
        "--tool-alias",
        action="append",
        default=[],
        metavar="SOURCE=TARGET",
        help="Map a retired frozen tool name to a current ToolSpec for execution only.",
    )
    parser.add_argument("--resume", action="store_true")
    return parser


def _parse_tool_base_urls(values: Sequence[str], registry) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    for value in values:
        tool_name, separator, base_url = value.partition("=")
        tool_name, base_url = tool_name.strip(), base_url.strip().rstrip("/")
        if not separator or not tool_name or not base_url:
            raise ValueError(f"Invalid --tool-base-url {value!r}; expected TOOL=URL")
        if tool_name in urls:
            raise ValueError(f"Duplicate remote tool URL for {tool_name!r}")
        registry.get(tool_name)
        urls[tool_name] = base_url
    return urls


def oracle_run_record(
    record: Mapping[str, Any],
    executor: AgentExecutor,
    registry,
    tool_aliases: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    request_id, gold_request, _ = extract_gold(record)
    prediction = canonical_json(gold_request)
    aliases = dict(tool_aliases or {})
    execution_request = _execution_request_with_aliases(gold_request, aliases, registry)
    execution_prediction = canonical_json(execution_request)
    total_started = time.perf_counter()
    execution, parsed_request, execution_ms = _execute_prediction(
        execution_prediction,
        request_id,
        f"{CONDITION}_final",
        executor,
        registry,
        record,
    )
    if parsed_request is None:
        raise RuntimeError(f"Frozen gold AgentRequest {request_id!r} failed schema parsing")
    return {
        "id": request_id,
        "condition": CONDITION,
        "prediction": prediction,
        "executed_request": execution_request,
        "execution": execution,
        "expert_invocation_count": _invocation_count(execution),
        "timing": {
            "planner_ms": 0.0,
            "execution_ms": execution_ms,
            "total_ms": (time.perf_counter() - total_started) * 1000.0,
            "model_load_excluded": True,
        },
        "generated_tokens": 0,
        "trace": [
            {
                "round": 0,
                "source": "frozen_gold_agent_request",
                "prediction": prediction,
                "generated_tokens": 0,
                "planner_ms": 0.0,
            }
        ],
        "oracle": {
            "routing_source": "frozen_gold_agent_request",
            "planner_executed": False,
            "claim_scope": "gold_policy_execution_reference",
            "execution_tool_aliases": aliases,
        },
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
    tool_aliases = _parse_tool_aliases(args.tool_alias, registry)
    tool_base_urls = _parse_tool_base_urls(args.tool_base_url, registry)
    if sum(bool(value) for value in (args.agent_service_url, args.expert_base_url, tool_base_urls)) > 1:
        raise ValueError(
            "Use only one of --agent-service-url, --expert-base-url, or --tool-base-url"
        )
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
        if args.expert_base_url:
            runtime = build_remote_runtime(
                registry,
                base_url=args.expert_base_url,
                work_dir=args.expert_work_dir,
                timeout_seconds=args.expert_timeout_seconds,
            )
        else:
            runtime = load_expert_runtime(args.runtime, registry, work_dir=args.expert_work_dir)
            if tool_base_urls:
                runtime = overlay_remote_tools(
                    runtime,
                    tool_base_urls=tool_base_urls,
                    work_dir=Path(args.expert_work_dir) / "remote_clients",
                    timeout_seconds=args.expert_timeout_seconds,
                )
        executor = AgentExecutor(runtime, args.execution_work_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = _completed_ids(output) if args.resume else set()
    mode = "a" if args.resume and output.exists() else "w"
    try:
        records = read_jsonl(input_path)
        if args.action_type:
            selected_types = set(args.action_type)
            records = [
                record
                for record in records
                if str(extract_gold(record)[1]["action"]["type"]) in selected_types
            ]
        if args.max_records is not None:
            if args.max_records < 0:
                raise ValueError("--max-records must be non-negative")
            records = records[: args.max_records]
        with output.open(mode, encoding="utf-8", newline="\n") as handle:
            for index, record in enumerate(records, start=1):
                if str(record["id"]) in completed:
                    continue
                row = oracle_run_record(
                    record,
                    executor,
                    registry,
                    tool_aliases=tool_aliases,
                )
                handle.write(canonical_json(row) + "\n")
                handle.flush()
                print(
                    f"ORACLE_E2E_REQUEST_OK index={index} id={row['id']} "
                    f"status={row['execution']['status']} "
                    f"total_ms={row['timing']['total_ms']:.1f}",
                    flush=True,
                )
    finally:
        if runtime is not None:
            runtime.shutdown()
        else:
            executor.shutdown()
    print(
        f"ORACLE_E2E_CONDITION_OK input_sha256={input_sha256} output={output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
