from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from hydro_remote_agent.backbones.external_vlm import ExternalVLMGenerator
from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json, read_jsonl
from hydro_remote_agent.runtime import build_remote_runtime, load_expert_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.run_agent_e2e_condition import _completed_ids, _run_record
from hydro_remote_agent.workflow import AgentExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an independent external VLM on the frozen Agent E2E protocol."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-path")
    parser.add_argument("--registry", default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml"))
    parser.add_argument("--runtime", default=str(PACKAGE_ROOT / "configs" / "expert_runtime.yaml"))
    parser.add_argument("--expert-base-url")
    parser.add_argument("--agent-service-url")
    parser.add_argument("--agent-artifact-proxy-url")
    parser.add_argument("--service-idempotency-namespace", default="task-aware-240")
    parser.add_argument("--expert-timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--service-poll-seconds", type=float, default=0.5)
    parser.add_argument("--expert-work-dir", required=True)
    parser.add_argument("--execution-work-dir", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--max-image-pixels", type=int)
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config: Mapping[str, Any] = json.loads(Path(args.config).read_text(encoding="utf-8"))
    condition = str(config.get("condition", "")).strip()
    if not condition:
        raise ValueError("External baseline config must declare a non-empty condition")
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
    generator = ExternalVLMGenerator(
        config=config,
        model_path=str(args.model_path or config["local_path"]),
        max_new_tokens=args.max_new_tokens,
        max_image_pixels=int(args.max_image_pixels or config["max_image_pixels"]),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = _completed_ids(output) if args.resume else set()
    mode = "a" if args.resume and output.exists() else "w"
    try:
        records = read_jsonl(Path(args.input))
        if args.max_records is not None:
            if args.max_records < 0:
                raise ValueError("--max-records must be non-negative")
            records = records[: args.max_records]
        with output.open(mode, encoding="utf-8", newline="\n") as handle:
            for index, record in enumerate(records, start=1):
                if str(record["id"]) in completed:
                    continue
                row: Dict[str, Any] = _run_record(
                    record,
                    condition,
                    generator,
                    executor,
                    registry,
                )
                row["model"] = {
                    "family": str(config["family"]),
                    "model_id": str(config["model_id"]),
                    "revision": str(config["revision"]),
                    "max_image_pixels": int(
                        args.max_image_pixels or config["max_image_pixels"]
                    ),
                    "enable_thinking": bool(config.get("enable_thinking", False)),
                    "constraint_mode": str(config.get("constraint_mode", "none")),
                }
                handle.write(canonical_json(row) + "\n")
                handle.flush()
                print(
                    f"EXTERNAL_AGENT_REQUEST_OK index={index} id={row['id']} "
                    f"status={row['execution']['status']} total_ms={row['timing']['total_ms']:.1f}",
                    flush=True,
                )
    finally:
        if runtime is not None:
            runtime.shutdown()
        else:
            executor.shutdown()
    print(f"EXTERNAL_AGENT_CONDITION_OK condition={condition} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
