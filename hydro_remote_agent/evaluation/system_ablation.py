from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Tuple

from .execution import summarize_execution
from .routing import iter_jsonl


SYSTEM_ABLATION_SCHEMA_VERSION = "vague_hydro.system_ablation.v1"
ABLATION_MODES = ("no_verifier", "no_workflow", "no_language_expert")
LANGUAGE_TOOL = "language_guided_point_segmentation"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _result(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("result")
    return value if isinstance(value, Mapping) else {}


def _required_tools(row: Mapping[str, Any]) -> Tuple[str, ...]:
    tools = _result(row).get("required_tools", row.get("required_tools", []))
    if not isinstance(tools, list):
        return ()
    return tuple(str(tool) for tool in tools)


def _quality_verdicts(row: Mapping[str, Any]) -> Counter[str]:
    verdicts: Counter[str] = Counter()
    workflow = _result(row).get("workflow_result")
    if not isinstance(workflow, Mapping):
        return verdicts
    steps = workflow.get("steps", [])
    if not isinstance(steps, list):
        return verdicts
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        verification = step.get("verification_result")
        if not isinstance(verification, Mapping):
            continue
        metrics = verification.get("metrics")
        verdict = metrics.get("verdict") if isinstance(metrics, Mapping) else None
        verdicts[str(verdict or "unknown")] += 1
    return verdicts


def _remove_values(mapping: MutableMapping[str, Any], removed_values: set[str]) -> None:
    for key, value in list(mapping.items()):
        if str(value) in removed_values:
            del mapping[key]


def _strip_verifier(row: Dict[str, Any]) -> Tuple[int, float]:
    result = row.get("result")
    if not isinstance(result, dict):
        return 0, 0.0
    workflow = result.get("workflow_result")
    if not isinstance(workflow, dict) or not isinstance(workflow.get("steps"), list):
        return 0, 0.0

    removed_count = 0
    removed_duration_ms = 0.0
    removed_artifacts: set[str] = set()
    removed_warnings: Counter[str] = Counter()
    for step in workflow["steps"]:
        if not isinstance(step, dict):
            continue
        verification = step.get("verification_result")
        if not isinstance(verification, dict):
            continue
        removed_count += 1
        duration = verification.get("duration_ms")
        if isinstance(duration, (int, float)):
            removed_duration_ms += float(duration)
        artifacts = verification.get("artifacts")
        if isinstance(artifacts, Mapping):
            removed_artifacts.update(str(value) for value in artifacts.values())
        warnings = verification.get("warnings")
        if isinstance(warnings, list):
            removed_warnings.update(str(value) for value in warnings)
        step["verification_result"] = None

    for container in (workflow, result):
        artifacts = container.get("terminal_artifacts")
        if isinstance(artifacts, dict):
            _remove_values(artifacts, removed_artifacts)
        warnings = container.get("warnings")
        if isinstance(warnings, list) and removed_warnings:
            remaining = removed_warnings.copy()
            kept = []
            for warning in warnings:
                text = str(warning)
                if remaining[text] > 0:
                    remaining[text] -= 1
                else:
                    kept.append(warning)
            container["warnings"] = kept
        duration = container.get("duration_ms")
        if isinstance(duration, (int, float)):
            container["duration_ms"] = max(0.0, float(duration) - removed_duration_ms)
    return removed_count, removed_duration_ms


def _blocked_result(source: Mapping[str, Any], mode: str, reason: str) -> Dict[str, Any]:
    result = _result(source)
    return {
        "schema_version": result.get("schema_version", "1.0"),
        "request_id": result.get("request_id", source.get("id")),
        "execution_id": result.get("execution_id"),
        "status": "blocked",
        "action_type": result.get("action_type", source.get("action_type", "unknown")),
        "intent": result.get("intent"),
        "execution_mode": "ablation_blocked",
        "outcome": reason,
        "response": None,
        "required_tools": list(_required_tools(source)),
        "terminal_artifacts": {},
        "workflow_result": None,
        "manifest_path": None,
        "duration_ms": 0.0,
        "error": {
            "code": reason,
            "message": f"Request blocked by system ablation {mode!r}.",
        },
        "is_mock": False,
        "warnings": [],
        "ablation_mode": mode,
    }


def transform_row(row: Mapping[str, Any], mode: str) -> Tuple[Dict[str, Any], Dict[str, float]]:
    if mode not in ABLATION_MODES:
        raise ValueError(f"Unsupported system ablation mode {mode!r}")
    transformed = copy.deepcopy(dict(row))
    result = _result(row)
    diagnostics = {"affected": 0.0, "removed_verifiers": 0.0, "removed_duration_ms": 0.0}

    if mode == "no_verifier":
        removed_count, removed_duration = _strip_verifier(transformed)
        diagnostics.update(
            affected=float(removed_count > 0),
            removed_verifiers=float(removed_count),
            removed_duration_ms=removed_duration,
        )
    elif mode == "no_workflow" and result.get("action_type") == "workflow":
        transformed["status"] = "blocked"
        transformed["result"] = _blocked_result(row, mode, "workflow_unavailable")
        diagnostics["affected"] = 1.0
    elif mode == "no_language_expert" and LANGUAGE_TOOL in _required_tools(row):
        transformed["status"] = "blocked"
        transformed["result"] = _blocked_result(row, mode, "language_expert_unavailable")
        diagnostics["affected"] = 1.0

    transformed["system_ablation"] = {"mode": mode, "derived_from_completed_execution": True}
    return transformed, diagnostics


def _ablation_metrics(rows: list[Mapping[str, Any]], mode: str) -> Dict[str, Any]:
    status_counts: Counter[str] = Counter()
    verdict_counts: Counter[str] = Counter()
    workflow_count = workflow_succeeded = 0
    language_count = language_succeeded = 0
    expert_count = expert_succeeded = 0
    durations = []
    for row in rows:
        status = str(row.get("status", "unknown"))
        status_counts[status] += 1
        verdict_counts.update(_quality_verdicts(row))
        result = _result(row)
        action_type = result.get("action_type", row.get("action_type"))
        tools = _required_tools(row)
        if action_type == "workflow":
            workflow_count += 1
            workflow_succeeded += int(status == "succeeded")
        if LANGUAGE_TOOL in tools:
            language_count += 1
            language_succeeded += int(status == "succeeded")
        if tools:
            expert_count += 1
            expert_succeeded += int(status == "succeeded")
        duration = result.get("duration_ms")
        if isinstance(duration, (int, float)):
            durations.append(float(duration))

    total = len(rows)
    verifier_count = sum(verdict_counts.values())
    return {
        "mode": mode,
        "request_count": total,
        "task_success_count": status_counts["succeeded"],
        "task_success_rate": status_counts["succeeded"] / total if total else None,
        "expert_request_count": expert_count,
        "expert_request_success_rate": expert_succeeded / expert_count if expert_count else None,
        "workflow_request_count": workflow_count,
        "workflow_success_rate": workflow_succeeded / workflow_count if workflow_count else None,
        "language_request_count": language_count,
        "language_request_success_rate": language_succeeded / language_count if language_count else None,
        "verification_count": verifier_count,
        "verification_coverage_rate": verifier_count / expert_succeeded if expert_succeeded else None,
        "quality_verdict_counts": dict(sorted(verdict_counts.items())),
        "mean_duration_ms": sum(durations) / len(durations) if durations else None,
        "total_duration_ms": sum(durations),
    }


def run_system_ablation(
    prediction_path: Path,
    baseline_results_path: Path,
    output_path: Path,
    report_path: Path,
    mode: str,
) -> Dict[str, Any]:
    if mode not in ABLATION_MODES:
        raise ValueError(f"Unsupported system ablation mode {mode!r}")
    source_rows = [dict(row) for _, row in iter_jsonl(baseline_results_path)]
    source_ids = [str(row.get("id", "")) for row in source_rows]
    if not source_ids or any(not row_id for row_id in source_ids):
        raise ValueError("Baseline results must contain non-empty request IDs")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Baseline results contain duplicate request IDs")

    transformed_rows = []
    affected_count = 0
    removed_verifier_count = 0
    removed_verifier_duration_ms = 0.0
    source_verdicts: Counter[str] = Counter()
    for row in source_rows:
        source_verdicts.update(_quality_verdicts(row))
        transformed, diagnostics = transform_row(row, mode)
        transformed_rows.append(transformed)
        affected_count += int(diagnostics["affected"])
        removed_verifier_count += int(diagnostics["removed_verifiers"])
        removed_verifier_duration_ms += diagnostics["removed_duration_ms"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in transformed_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    baseline_metrics = _ablation_metrics(source_rows, "baseline")
    metrics = _ablation_metrics(transformed_rows, mode)
    delta_keys = (
        "task_success_rate",
        "expert_request_success_rate",
        "workflow_success_rate",
        "language_request_success_rate",
        "verification_coverage_rate",
        "mean_duration_ms",
    )
    metric_deltas = {
        key: metrics[key] - baseline_metrics[key]
        for key in delta_keys
        if isinstance(metrics.get(key), (int, float))
        and isinstance(baseline_metrics.get(key), (int, float))
    }
    report = summarize_execution(prediction_path, output_path)
    report.update(
        schema_version=SYSTEM_ABLATION_SCHEMA_VERSION,
        ablation={
            "mode": mode,
            "derived_from_completed_execution": True,
            "baseline_results": str(baseline_results_path),
            "baseline_results_sha256": _sha256(baseline_results_path),
            "affected_request_count": affected_count,
            "removed_verifier_count": removed_verifier_count,
            "removed_verifier_duration_ms": removed_verifier_duration_ms,
            "source_quality_verdict_counts": dict(sorted(source_verdicts.items())),
        },
        baseline_metrics=baseline_metrics,
        metrics=metrics,
        metric_deltas=metric_deltas,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return report
