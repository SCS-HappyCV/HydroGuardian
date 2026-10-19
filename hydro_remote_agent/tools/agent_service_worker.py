from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.runtime import build_remote_runtime, load_expert_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.store_factory import create_job_store
from hydro_remote_agent.service.worker import ExecutorWorker, PlannerWorker, run_worker_loop
from hydro_remote_agent.service.infra import NullEventBus, RabbitEventBus
from hydro_remote_agent.workflow import AgentExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a VagueHydro Agent queue worker.")
    parser.add_argument("role", choices=("planner", "executor"))
    parser.add_argument("--db", required=True)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument(
        "--registry", default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
    )
    parser.add_argument("--worker-id")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--lease-seconds", type=float)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument(
        "--transient-retry-delay-seconds",
        type=float,
        default=float(os.getenv("EXECUTOR_TRANSIENT_RETRY_DELAY_SECONDS", "15")),
    )
    parser.add_argument("--once", action="store_true")

    parser.add_argument(
        "--backbone-config",
        default=str(PACKAGE_ROOT / "configs" / "backbone_qwen3_vl_8b.json"),
    )
    parser.add_argument("--model-path")
    parser.add_argument("--adapter-path")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--max-image-pixels", type=int, default=262144)
    parser.add_argument("--planner-backend", choices=("semantic", "qwen"), default=os.getenv("PLANNER_BACKEND", "qwen"))

    parser.add_argument(
        "--runtime", default=str(PACKAGE_ROOT / "configs" / "expert_runtime.yaml")
    )
    parser.add_argument("--expert-work-dir")
    parser.add_argument("--execution-work-dir")
    parser.add_argument("--expert-base-url")
    parser.add_argument("--expert-api-prefix", default="/v1")
    parser.add_argument("--rabbitmq-url", default=os.getenv("RABBITMQ_URL", ""))
    parser.add_argument("--expert-timeout-seconds", type=float, default=600.0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    registry = load_tool_registry(args.registry)
    store = create_job_store(args.database_url or args.db)
    event_bus = RabbitEventBus(args.rabbitmq_url) if args.rabbitmq_url else NullEventBus()
    if args.role == "planner":
        from hydro_remote_agent.service.planner import Qwen3VLPlannerBackend, SemanticPlannerBackend

        backend = SemanticPlannerBackend(registry) if args.planner_backend == "semantic" else Qwen3VLPlannerBackend(
            config_path=args.backbone_config, registry=registry, model_path=args.model_path,
            adapter_path=args.adapter_path, max_new_tokens=args.max_new_tokens,
            max_image_pixels=args.max_image_pixels,
        )
        worker = PlannerWorker(
            store,
            backend,
            registry,
            worker_id=args.worker_id,
            lease_seconds=(args.lease_seconds if args.lease_seconds is not None else 1800.0),
            event_bus=event_bus,
        )
        run_worker_loop(worker, poll_seconds=args.poll_seconds, once=args.once)
        return 0

    if not args.expert_work_dir or not args.execution_work_dir:
        raise ValueError("executor requires --expert-work-dir and --execution-work-dir")
    if args.expert_base_url:
        runtime = build_remote_runtime(
            registry,
            base_url=args.expert_base_url,
            work_dir=args.expert_work_dir,
            timeout_seconds=args.expert_timeout_seconds,
            api_prefix=args.expert_api_prefix,
        )
    else:
        runtime = load_expert_runtime(
            args.runtime,
            registry,
            work_dir=args.expert_work_dir,
        )
    try:
        worker = ExecutorWorker(
            store,
            AgentExecutor(runtime, args.execution_work_dir),
            registry,
            worker_id=args.worker_id,
            lease_seconds=(args.lease_seconds if args.lease_seconds is not None else 3600.0),
            event_bus=event_bus,
            max_attempts=args.max_attempts,
            transient_retry_delay_seconds=args.transient_retry_delay_seconds,
        )
        run_worker_loop(worker, poll_seconds=args.poll_seconds, once=args.once)
    finally:
        runtime.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
