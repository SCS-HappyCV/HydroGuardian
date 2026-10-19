from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Sequence, Tuple

from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import ToolRegistry
from hydro_remote_agent.workflow import AgentExecutor

from .routing import extract_prediction, iter_jsonl, parse_json_response


EXECUTION_EVALUATION_SCHEMA_VERSION = "vague_hydro.execution_eval.v1"


def _execution_id(query_id: str, index: int, work_dir: Path) -> str:
    digest = hashlib.sha256(query_id.encode("utf-8")).hexdigest()[:12]
    base = f"e2e_{index:04d}_{digest}"
    candidate = base
    retry = 1
    while (work_dir / candidate).exists():
        candidate = f"{base}_r{retry}"
        retry += 1
    return candidate


def _completed_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {
        str(row.get("id", ""))
        for _, row in iter_jsonl(path)
        if row.get("id") and row.get("status") != "failed"
    }


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def _execution_outcome(result: Mapping[str, Any], status: str) -> str:
    explicit = result.get("outcome")
    if isinstance(explicit, str) and explicit:
        return explicit
    mode = str(result.get("execution_mode", ""))
    if mode == "planner_only":
        return "response"
    if mode == "skipped_mock":
        return "skipped_mock"
    if mode == "expert_runtime":
        return "result" if status == "succeeded" else "execution_failed"
    return "unknown"


def execute_predictions(
    prediction_path: Path,
    output_path: Path,
    executor: AgentExecutor,
    registry: ToolRegistry,
    max_expert_executions: Optional[int] = None,
    skip_mock: bool = True,
) -> Dict[str, Any]:
    completed = _completed_ids(output_path)
    input_count = 0
    resumed_count = 0
    written_count = 0
    expert_attempts = 0
    deferred_count = 0
    schema_error_count = 0

    for index, (_, row) in enumerate(iter_jsonl(prediction_path), start=1):
        input_count += 1
        query_id, raw_prediction = extract_prediction(row)
        if query_id in completed:
            resumed_count += 1
            continue
        try:
            request_payload = parse_json_response(raw_prediction)
            request = AgentRequest.from_dict(request_payload, registry)
        except Exception as exc:
            schema_error_count += 1
            _append_jsonl(
                output_path,
                {
                    "id": query_id,
                    "status": "invalid_request",
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            written_count += 1
            continue

        requires_experts = bool(executor.required_tools(request))
        requires_mock = bool(executor.mock_tools(request))
        if requires_experts and not (requires_mock and skip_mock):
            if max_expert_executions is not None and expert_attempts >= max_expert_executions:
                deferred_count += 1
                continue
            expert_attempts += 1

        execution_id = _execution_id(query_id, index, executor.work_dir)
        try:
            result = executor.execute(
                request,
                execution_id=execution_id,
                skip_mock=skip_mock,
            )
            output = {
                "id": query_id,
                "status": result.status,
                "result": result.to_dict(),
            }
        except Exception as exc:
            output = {
                "id": query_id,
                "status": "failed",
                "execution_id": execution_id,
                "action_type": request.action.type,
                "required_tools": list(executor.required_tools(request)),
                "error": f"{type(exc).__name__}: {exc}",
            }
        _append_jsonl(output_path, output)
        written_count += 1

    return {
        "input_count": input_count,
        "resumed_count": resumed_count,
        "written_count": written_count,
        "expert_attempt_count": expert_attempts,
        "deferred_expert_count": deferred_count,
        "schema_error_count": schema_error_count,
    }


def summarize_execution(
    prediction_path: Path,
    output_path: Path,
    run_stats: Optional[Mapping[str, Any]] = None,
    max_error_examples: int = 20,
) -> Dict[str, Any]:
    action_counts: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    mode_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    errors = []
    real_attempted = 0
    real_succeeded = 0
    real_failed = 0
    mock_skipped = 0
    planner_succeeded = 0
    artifact_count = 0
    existing_artifact_count = 0
    verifier_count = 0
    verifier_succeeded = 0
    verifier_verdict_counts: Counter[str] = Counter()

    latest_rows: Dict[str, Dict[str, Any]] = {}
    for _, row in iter_jsonl(output_path):
        row_id = str(row.get("id", ""))
        if row_id:
            latest_rows[row_id] = row

    for row in latest_rows.values():
        status = str(row.get("status", "unknown"))
        status_counts[status] += 1
        result = row.get("result")
        if not isinstance(result, dict):
            action_type = str(row.get("action_type", "unknown"))
            required_tools = row.get("required_tools", [])
            action_counts[action_type] += 1
            if isinstance(required_tools, list) and required_tools:
                real_attempted += 1
                real_failed += 1
                mode_counts["expert_runtime"] += 1
                for tool in required_tools:
                    tool_counts[str(tool)] += 1
            if len(errors) < max_error_examples:
                errors.append({"id": row.get("id"), "error": row.get("error")})
            continue
        action_type = str(result.get("action_type", "unknown"))
        mode = str(result.get("execution_mode", "unknown"))
        outcome = _execution_outcome(result, status)
        action_counts[action_type] += 1
        mode_counts[mode] += 1
        outcome_counts[outcome] += 1
        for tool in result.get("required_tools", []):
            tool_counts[str(tool)] += 1
        if mode == "planner_only" and status == "succeeded":
            planner_succeeded += 1
        elif mode == "skipped_mock":
            mock_skipped += 1
        elif mode == "expert_runtime":
            real_attempted += 1
            if status == "succeeded" and not result.get("is_mock", False):
                real_succeeded += 1
            else:
                real_failed += 1
        for artifact in result.get("terminal_artifacts", {}).values():
            artifact_count += 1
            existing_artifact_count += int(Path(str(artifact)).is_file())
        workflow = result.get("workflow_result")
        if isinstance(workflow, dict):
            for step in workflow.get("steps", []):
                if not isinstance(step, dict) or step.get("verification_result") is None:
                    continue
                verifier_count += 1
                verification = step["verification_result"]
                verifier_succeeded += int(
                    isinstance(verification, dict)
                    and verification.get("status") == "succeeded"
                )
                if isinstance(verification, dict):
                    metrics = verification.get("metrics")
                    if isinstance(metrics, Mapping) and metrics.get("verdict"):
                        verifier_verdict_counts[str(metrics["verdict"])] += 1
        if status != "succeeded" and mode != "skipped_mock" and len(errors) < max_error_examples:
            error = result.get("error")
            errors.append({"id": row.get("id"), "error": error})

    input_count = sum(1 for _ in iter_jsonl(prediction_path))
    completed_count = len(latest_rows)
    return {
        "schema_version": EXECUTION_EVALUATION_SCHEMA_VERSION,
        "status": "completed" if completed_count == input_count else "partial",
        "input_count": input_count,
        "completed_count": completed_count,
        "pending_count": input_count - completed_count,
        "run_stats": dict(run_stats or {}),
        "status_counts": dict(sorted(status_counts.items())),
        "execution_mode_counts": dict(sorted(mode_counts.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "action_type_counts": dict(sorted(action_counts.items())),
        "required_tool_counts": dict(sorted(tool_counts.items())),
        "planner_succeeded_count": planner_succeeded,
        "mock_skipped_count": mock_skipped,
        "real_expert_attempted_count": real_attempted,
        "real_expert_succeeded_count": real_succeeded,
        "real_expert_failed_count": real_failed,
        "real_expert_success_rate": (
            real_succeeded / real_attempted if real_attempted else None
        ),
        "real_expert_result_count": outcome_counts["result"],
        "real_expert_no_target_count": outcome_counts["no_target"],
        "real_expert_no_reference_count": outcome_counts["no_reference"],
        "terminal_artifact_count": artifact_count,
        "existing_terminal_artifact_count": existing_artifact_count,
        "terminal_artifact_existence_rate": (
            existing_artifact_count / artifact_count if artifact_count else None
        ),
        "verifier_count": verifier_count,
        "verifier_succeeded_count": verifier_succeeded,
        "verifier_verdict_counts": dict(sorted(verifier_verdict_counts.items())),
        "verifier_success_rate": (
            verifier_succeeded / verifier_count if verifier_count else None
        ),
        "error_examples": errors,
    }


def merge_execution_results(
    prediction_path: Path,
    base_result_path: Path,
    replacement_result_path: Path,
    output_path: Path,
) -> Dict[str, Any]:
    """Replace skipped-mock rows while preserving the frozen prediction order."""
    prediction_ids = [extract_prediction(row)[0] for _, row in iter_jsonl(prediction_path)]
    if len(prediction_ids) != len(set(prediction_ids)):
        raise ValueError("Prediction file contains duplicate request IDs")

    def latest_rows(path: Path) -> Dict[str, Dict[str, Any]]:
        rows: Dict[str, Dict[str, Any]] = {}
        for _, row in iter_jsonl(path):
            row_id = str(row.get("id", ""))
            if not row_id:
                raise ValueError(f"Execution row in {path} is missing id")
            rows[row_id] = dict(row)
        return rows

    base_rows = latest_rows(base_result_path)
    replacement_rows = latest_rows(replacement_result_path)
    expected_ids = set(prediction_ids)
    if set(base_rows) != expected_ids:
        missing = sorted(expected_ids - set(base_rows))
        unknown = sorted(set(base_rows) - expected_ids)
        raise ValueError(f"Base result IDs differ from predictions: missing={missing[:5]} unknown={unknown[:5]}")

    skipped_ids = {
        row_id
        for row_id, row in base_rows.items()
        if isinstance(row.get("result"), Mapping)
        and row["result"].get("execution_mode") == "skipped_mock"
    }
    if set(replacement_rows) != skipped_ids:
        missing = sorted(skipped_ids - set(replacement_rows))
        unknown = sorted(set(replacement_rows) - skipped_ids)
        raise ValueError(
            f"Replacement IDs must exactly match skipped-mock IDs: missing={missing[:5]} unknown={unknown[:5]}"
        )
    invalid_replacements = sorted(
        row_id
        for row_id, row in replacement_rows.items()
        if row.get("status") != "succeeded"
        or not isinstance(row.get("result"), Mapping)
        or row["result"].get("execution_mode") != "expert_runtime"
        or bool(row["result"].get("is_mock", False))
    )
    if invalid_replacements:
        raise ValueError(f"Replacement rows are not successful real executions: {invalid_replacements[:5]}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row_id in prediction_ids:
            row = replacement_rows.get(row_id, base_rows[row_id])
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "prediction_count": len(prediction_ids),
        "base_count": len(base_rows),
        "replacement_count": len(replacement_rows),
        "replaced_ids": sorted(replacement_rows),
        "remaining_skipped_mock_count": 0,
    }
