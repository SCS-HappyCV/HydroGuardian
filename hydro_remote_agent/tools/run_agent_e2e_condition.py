from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from hydro_remote_agent.backbones.qwen3_vl_planner import (
    canonical_json,
    planner_messages,
    read_jsonl,
)
from hydro_remote_agent.baselines.tool_observation_react import (
    compact_execution_observation,
    final_messages,
    initial_messages,
)
from hydro_remote_agent.evaluation.routing import parse_json_response
from hydro_remote_agent.runtime import build_remote_runtime, load_expert_runtime
from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.workflow import AgentExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = ("tool_observation_react", "vaguehydro_lora")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one frozen Agent E2E comparison condition.")
    parser.add_argument("--condition", choices=CONDITIONS, required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--adapter-path")
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
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--max-image-pixels", type=int)
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--resume", action="store_true")
    return parser


class Generator:
    def __init__(
        self,
        config: Mapping[str, Any],
        model_path: str,
        adapter_path: Optional[str],
        max_image_pixels: int,
        max_new_tokens: int,
    ) -> None:
        import torch
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

        self.torch = torch
        self.max_new_tokens = max(max_new_tokens, 1)
        self.processor = AutoProcessor.from_pretrained(
            model_path,
            max_pixels=max_image_pixels,
            local_files_only=True,
            trust_remote_code=bool(config.get("trust_remote_code", False)),
        )
        self.processor.tokenizer.padding_side = "left"
        dtype = torch.bfloat16 if config.get("dtype") == "bfloat16" else torch.float16
        started = time.perf_counter()
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            dtype=dtype,
            device_map={"": 0},
            attn_implementation="sdpa",
            local_files_only=True,
            trust_remote_code=bool(config.get("trust_remote_code", False)),
        )
        if adapter_path:
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, adapter_path)
        self.model = model.eval()
        print(f"E2E_BACKBONE_READY seconds={time.perf_counter() - started:.2f}", flush=True)

    def generate(self, messages: List[Dict[str, Any]]) -> Tuple[str, int, float]:
        inputs = self.processor.apply_chat_template(
            [messages],
            tokenize=True,
            add_generation_prompt=True,
            padding=True,
            return_dict=True,
            return_tensors="pt",
        ).to("cuda")
        started = time.perf_counter()
        with self.torch.inference_mode():
            generated = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
            )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        trimmed = generated[:, inputs["input_ids"].shape[1] :]
        token_count = int(
            (trimmed[0] != self.processor.tokenizer.pad_token_id).sum().item()
        )
        text = self.processor.batch_decode(
            trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()
        return text, token_count, elapsed_ms


def _completed_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {str(row.get("id", "")) for row in read_jsonl(path) if row.get("id")}


def _invocation_count(execution: Mapping[str, Any]) -> int:
    result = execution.get("result")
    if not isinstance(result, Mapping):
        return 0
    workflow = result.get("workflow_result")
    if not isinstance(workflow, Mapping):
        return 0
    count = 0
    for step in workflow.get("steps", []):
        if not isinstance(step, Mapping) or step.get("status") == "skipped":
            continue
        count += 1
        count += int(isinstance(step.get("verification_result"), Mapping))
    return count


def _execute_prediction(
    prediction: str,
    request_id: str,
    phase: str,
    executor: AgentExecutor,
    registry,
    record: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], float]:
    if hasattr(executor, "execute_prediction"):
        if record is None:
            raise ValueError("Agent service execution requires the source record")
        return executor.execute_prediction(
            prediction,
            request_id,
            phase,
            record,
            registry,
        )
    started = time.perf_counter()
    parsed_payload: Optional[Dict[str, Any]] = None
    try:
        payload = parse_json_response(prediction)
        request = AgentRequest.from_dict(payload, registry)
        parsed_payload = payload
        if request.request_id != request_id:
            raise ValueError("Planner changed request_id")
        for tool_name in executor.required_tools(request):
            executor.runtime.prepare(tool_name)
        execution_id = f"e2e_{phase}_{hashlib_sha(request_id)}"
        result = executor.execute(request, execution_id=execution_id, skip_mock=True)
        execution = {"id": request_id, "status": result.status, "result": result.to_dict()}
        return execution, payload, (time.perf_counter() - started) * 1000.0
    except Exception as exc:
        return (
            {
                "id": request_id,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            },
            parsed_payload,
            (time.perf_counter() - started) * 1000.0,
        )


def hashlib_sha(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _run_record(
    record: Mapping[str, Any],
    condition: str,
    generator: Generator,
    executor: AgentExecutor,
    registry,
) -> Dict[str, Any]:
    request_id = str(record["id"])
    total_started = time.perf_counter()
    planner_ms = 0.0
    execution_ms = 0.0
    token_count = 0
    invocation_count = 0
    trace: List[Dict[str, Any]] = []

    first_messages = (
        initial_messages(record)
        if condition == "tool_observation_react"
        else planner_messages(record, prompt_profile="full")
    )
    initial_prediction, initial_tokens, initial_ms = generator.generate(first_messages)
    planner_ms += initial_ms
    token_count += initial_tokens

    if condition == "tool_observation_react":
        initial_execution, initial_payload, initial_execution_ms = _execute_prediction(
            initial_prediction,
            request_id,
            f"{condition}_observe",
            executor,
            registry,
            record,
        )
        execution_ms += initial_execution_ms
        invocation_count += _invocation_count(initial_execution)
        observation = compact_execution_observation(initial_execution)
        trace.append({
            "round": 1,
            "prediction": initial_prediction,
            "execution": initial_execution,
            "observation": observation,
            "generated_tokens": initial_tokens,
            "planner_ms": initial_ms,
        })
        prediction, final_tokens, final_ms = generator.generate(
            final_messages(record, initial_prediction, observation)
        )
        planner_ms += final_ms
        token_count += final_tokens
        try:
            final_payload = parse_json_response(prediction)
        except Exception:
            final_payload = None
        if initial_payload is not None and final_payload is not None and canonical_json(
            initial_payload
        ) == canonical_json(final_payload):
            execution = initial_execution
            reused_observed_execution = True
        else:
            execution, _, final_execution_ms = _execute_prediction(
                prediction,
                request_id,
                f"{condition}_final",
                executor,
                registry,
                record,
            )
            execution_ms += final_execution_ms
            invocation_count += _invocation_count(execution)
            reused_observed_execution = False
        trace.append({
            "round": 2,
            "prediction": prediction,
            "generated_tokens": final_tokens,
            "planner_ms": final_ms,
            "reused_observed_execution": reused_observed_execution,
        })
    else:
        prediction = initial_prediction
        execution, _, execution_ms = _execute_prediction(
            prediction,
            request_id,
            f"{condition}_final",
            executor,
            registry,
            record,
        )
        invocation_count = _invocation_count(execution)
        trace.append({
            "round": 1,
            "prediction": prediction,
            "generated_tokens": initial_tokens,
            "planner_ms": initial_ms,
        })

    return {
        "id": request_id,
        "condition": condition,
        "prediction": prediction,
        "execution": execution,
        "expert_invocation_count": invocation_count,
        "timing": {
            "planner_ms": planner_ms,
            "execution_ms": execution_ms,
            "total_ms": (time.perf_counter() - total_started) * 1000.0,
            "model_load_excluded": True,
        },
        "generated_tokens": token_count,
        "trace": trace,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.condition == "vaguehydro_lora" and not args.adapter_path:
        raise ValueError("vaguehydro_lora requires --adapter-path")
    if args.condition == "tool_observation_react" and args.adapter_path:
        raise ValueError("tool_observation_react uses the unadapted backbone")

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
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
    generator = Generator(
        config=config,
        model_path=str(args.model_path or config["local_path"]),
        adapter_path=args.adapter_path,
        max_image_pixels=int(args.max_image_pixels or config.get("max_image_pixels", 1048576)),
        max_new_tokens=args.max_new_tokens,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = _completed_ids(output) if args.resume else set()
    mode = "a" if args.resume and output.exists() else "w"
    try:
        with output.open(mode, encoding="utf-8", newline="\n") as handle:
            records = read_jsonl(Path(args.input))
            if args.max_records is not None:
                if args.max_records < 0:
                    raise ValueError("--max-records must be non-negative")
                records = records[: args.max_records]
            for index, record in enumerate(records, start=1):
                if str(record["id"]) in completed:
                    continue
                row = _run_record(record, args.condition, generator, executor, registry)
                handle.write(canonical_json(row) + "\n")
                handle.flush()
                print(
                    f"AGENT_E2E_REQUEST_OK condition={args.condition} index={index} "
                    f"id={row['id']} status={row['execution']['status']} "
                    f"total_ms={row['timing']['total_ms']:.1f}",
                    flush=True,
                )
    finally:
        if runtime is not None:
            runtime.shutdown()
        else:
            executor.shutdown()
    print(f"AGENT_E2E_CONDITION_OK condition={args.condition} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
