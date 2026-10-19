from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Set, Tuple

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json, read_jsonl
from hydro_remote_agent.evaluation.routing import parse_json_response, sha256_file
from hydro_remote_agent.runtime import load_expert_runtime, overlay_remote_tools
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.run_agent_e2e_condition import (
    _completed_ids,
    _execute_prediction,
    _invocation_count,
)
from hydro_remote_agent.tool_aliases import (
    execution_request_with_aliases as _execution_request_with_aliases,
    parse_tool_aliases as _parse_tool_aliases,
)
from hydro_remote_agent.tools.run_oracle_e2e_condition import _parse_tool_base_urls
from hydro_remote_agent.workflow import AgentExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay only frozen Agent requests affected by an expert replacement."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--expected-input-sha256")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--condition", required=True)
    parser.add_argument(
        "--registry", default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
    )
    parser.add_argument(
        "--runtime",
        default=str(PACKAGE_ROOT / "configs" / "expert_runtime.yaml"),
    )
    parser.add_argument("--tool-base-url", action="append", default=[], metavar="TOOL=URL")
    parser.add_argument("--tool-alias", action="append", default=[], metavar="SOURCE=TARGET")
    parser.add_argument("--replacement-tool", action="append", default=[])
    parser.add_argument("--reuse-run", action="append", default=[], type=Path)
    parser.add_argument("--expert-timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--expert-work-dir", required=True, type=Path)
    parser.add_argument("--execution-work-dir", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    return parser


def _request_tools(payload: Mapping[str, Any]) -> Set[str]:
    action = payload.get("action")
    if not isinstance(action, Mapping):
        return set()
    action_type = action.get("type")
    calls = [action] if action_type == "tool_call" else action.get("steps", [])
    if not isinstance(calls, list):
        return set()
    return {
        str(call["tool"])
        for call in calls
        if isinstance(call, Mapping) and isinstance(call.get("tool"), str)
    }


def _load_reuse_cache(paths: Sequence[Path]) -> Dict[str, Mapping[str, Any]]:
    cache: Dict[str, Mapping[str, Any]] = {}
    for path in paths:
        for row in read_jsonl(path):
            executed_request = row.get("executed_request")
            execution = row.get("execution")
            if not isinstance(executed_request, Mapping) or not isinstance(execution, Mapping):
                continue
            if execution.get("status") != "succeeded":
                continue
            key = canonical_json(dict(executed_request))
            existing = cache.get(key)
            if existing is not None and existing.get("execution") != execution:
                raise ValueError(f"Conflicting reusable executions for request key from {path}")
            cache[key] = {
                "execution": copy.deepcopy(dict(execution)),
                "source_path": str(path),
                "source_id": str(row.get("id", "")),
            }
    return cache


def replay_record(
    source_row: Mapping[str, Any],
    condition: str,
    executor: AgentExecutor,
    registry,
    replacement_tools: Set[str],
    tool_aliases: Mapping[str, str],
    reuse_cache: Mapping[str, Mapping[str, Any]],
) -> Tuple[Dict[str, Any], str]:
    row = copy.deepcopy(dict(source_row))
    request_id = str(row["id"])
    raw_prediction = row.get("prediction")
    metadata: Dict[str, Any] = {
        "source_condition": str(source_row.get("condition", condition)),
        "replacement_tools": sorted(replacement_tools),
        "tool_aliases": dict(tool_aliases),
    }
    try:
        payload = parse_json_response(raw_prediction)
    except Exception as exc:
        metadata.update({"mode": "preserved", "reason": f"prediction_parse_failed:{type(exc).__name__}"})
        row["replacement_replay"] = metadata
        return row, "preserved"

    original_tools = _request_tools(payload)
    if not (original_tools & replacement_tools):
        metadata.update({"mode": "preserved", "reason": "replacement_tool_not_used"})
        row["replacement_replay"] = metadata
        return row, "preserved"

    execution_request = _execution_request_with_aliases(payload, tool_aliases, registry)
    execution_prediction = canonical_json(execution_request)
    cache_key = canonical_json(execution_request)
    cached = reuse_cache.get(cache_key)
    if cached is not None:
        execution = copy.deepcopy(dict(cached["execution"]))
        execution_ms = 0.0
        metadata.update(
            {
                "mode": "reused",
                "reason": "identical_executed_request",
                "reuse_source_path": cached["source_path"],
                "reuse_source_id": cached["source_id"],
            }
        )
        mode = "reused"
    else:
        execution, _, execution_ms = _execute_prediction(
            execution_prediction,
            request_id,
            f"{condition}_expert_replacement",
            executor,
            registry,
            source_row,
        )
        metadata.update({"mode": "executed", "reason": "replacement_tool_used"})
        mode = "executed"

    row["condition"] = condition
    row["executed_request"] = execution_request
    row["execution"] = execution
    row["expert_invocation_count"] = _invocation_count(execution)
    source_timing = row.get("timing")
    row["timing"] = {
        "planner_ms": 0.0,
        "execution_ms": execution_ms,
        "total_ms": execution_ms,
        "model_load_excluded": True,
        "frozen_prediction": True,
        "source_timing": source_timing,
    }
    row["replacement_replay"] = metadata
    return row, mode


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    actual_sha256 = sha256_file(args.input)
    if args.expected_input_sha256 and actual_sha256 != args.expected_input_sha256.lower():
        raise ValueError(
            f"Frozen input SHA256 mismatch: expected {args.expected_input_sha256.lower()}, got {actual_sha256}"
        )
    registry = load_tool_registry(args.registry)
    aliases = _parse_tool_aliases(args.tool_alias, registry)
    base_urls = _parse_tool_base_urls(args.tool_base_url, registry)
    replacement_tools = set(args.replacement_tool)
    if not replacement_tools:
        raise ValueError("At least one --replacement-tool is required")
    unknown_replacement_tools = sorted(
        replacement_tools - set(registry.names()) - set(aliases)
    )
    if unknown_replacement_tools:
        raise ValueError(f"Unknown replacement tools: {unknown_replacement_tools}")

    runtime = load_expert_runtime(args.runtime, registry, work_dir=args.expert_work_dir)
    if base_urls:
        runtime = overlay_remote_tools(
            runtime,
            tool_base_urls=base_urls,
            work_dir=args.expert_work_dir / "remote_clients",
            timeout_seconds=args.expert_timeout_seconds,
        )
    executor = AgentExecutor(runtime, args.execution_work_dir)
    reuse_cache = _load_reuse_cache(args.reuse_run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = _completed_ids(args.output) if args.resume else set()
    mode = "a" if args.resume and args.output.exists() else "w"
    counts = {"preserved": 0, "reused": 0, "executed": 0}
    try:
        records = read_jsonl(args.input)
        with args.output.open(mode, encoding="utf-8", newline="\n") as handle:
            for index, source_row in enumerate(records, start=1):
                if str(source_row.get("id", "")) in completed:
                    continue
                row, replay_mode = replay_record(
                    source_row,
                    args.condition,
                    executor,
                    registry,
                    replacement_tools,
                    aliases,
                    reuse_cache,
                )
                counts[replay_mode] += 1
                handle.write(canonical_json(row) + "\n")
                handle.flush()
                print(
                    f"FROZEN_REPLAY_OK index={index} id={row['id']} mode={replay_mode} "
                    f"status={row.get('execution', {}).get('status')}",
                    flush=True,
                )
    finally:
        runtime.shutdown()

    rows = read_jsonl(args.output)
    ids = [str(row.get("id", "")) for row in rows]
    if len(rows) != len(set(ids)):
        raise ValueError("Replay output contains duplicate request IDs")
    if len(rows) != len(read_jsonl(args.input)):
        raise ValueError(f"Replay output is incomplete: {len(rows)} rows")
    print(
        f"FROZEN_REPLAY_COMPLETE condition={args.condition} input_sha256={actual_sha256} "
        f"rows={len(rows)} preserved={counts['preserved']} reused={counts['reused']} "
        f"executed={counts['executed']} output={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
