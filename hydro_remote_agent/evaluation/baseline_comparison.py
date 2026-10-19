from __future__ import annotations

import json
import math
import random
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Mapping, Sequence, Tuple

from hydro_remote_agent.evaluation.routing import (
    canonical_json,
    extract_gold,
    iter_jsonl,
    load_predictions,
    parse_json_response,
    sha256_file,
)
from hydro_remote_agent.schemas.agent_action import AgentActionError, AgentRequest
from hydro_remote_agent.schemas.tool_spec import ToolRegistry, load_tool_registry


METRICS = (
    "parse_rate",
    "schema_valid_rate",
    "action_type_accuracy",
    "tool_selection_accuracy",
    "argument_slot_f1",
    "workflow_graph_accuracy",
    "request_exact_match",
)


def _action_type(request: Mapping[str, Any]) -> str:
    action = request.get("action")
    return str(action.get("type", "")) if isinstance(action, Mapping) else ""


def _tool_sequence(request: Mapping[str, Any]) -> Tuple[str, ...]:
    action = request.get("action")
    if not isinstance(action, Mapping):
        return ()
    if action.get("type") == "tool_call":
        return (str(action.get("tool", "")),)
    steps = action.get("steps")
    if action.get("type") == "workflow" and isinstance(steps, list):
        return tuple(str(step.get("tool", "")) for step in steps if isinstance(step, Mapping))
    return ()


def _binary_outcomes(
    gold_path: Path,
    prediction_path: Path,
    registry: ToolRegistry,
) -> Dict[str, Dict[str, int]]:
    predictions = load_predictions(prediction_path)
    outcomes: Dict[str, Dict[str, int]] = {}
    for _, row in iter_jsonl(gold_path):
        query_id, gold, _ = extract_gold(row)
        raw = predictions.get(query_id)
        prediction = None
        valid = False
        if raw is not None:
            try:
                prediction = parse_json_response(raw)
                AgentRequest.from_dict(prediction, registry)
                valid = True
            except (ValueError, AgentActionError):
                pass
        outcomes[query_id] = {
            "schema": int(valid),
            "action": int(valid and _action_type(gold) == _action_type(prediction or {})),
            "tool": int(valid and _tool_sequence(gold) == _tool_sequence(prediction or {})),
            "exact": int(valid and canonical_json(gold) == canonical_json(prediction)),
        }
    return outcomes


def _paired_bootstrap(
    baseline: Sequence[int],
    candidate: Sequence[int],
    samples: int,
    seed: int,
) -> Dict[str, float]:
    if len(baseline) != len(candidate) or not baseline:
        raise ValueError("paired bootstrap requires equally sized non-empty outcomes")
    rng = random.Random(seed)
    n = len(baseline)
    deltas = []
    for _ in range(samples):
        indices = [rng.randrange(n) for _ in range(n)]
        deltas.append(mean(candidate[i] - baseline[i] for i in indices))
    deltas.sort()
    lower_index = max(int(samples * 0.025), 0)
    upper_index = min(int(samples * 0.975), samples - 1)
    return {
        "delta": mean(c - b for b, c in zip(baseline, candidate)),
        "lower": deltas[lower_index],
        "upper": deltas[upper_index],
    }


def _mcnemar_exact(baseline: Sequence[int], candidate: Sequence[int]) -> Dict[str, Any]:
    improved = sum(int(b == 0 and c == 1) for b, c in zip(baseline, candidate))
    regressed = sum(int(b == 1 and c == 0) for b, c in zip(baseline, candidate))
    discordant = improved + regressed
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, k) for k in range(min(improved, regressed) + 1))
        p_value = min(1.0, 2.0 * tail / (2 ** discordant))
    return {"improved": improved, "regressed": regressed, "p_value_two_sided": p_value}


def _inference_summary(path: Path) -> Dict[str, Any]:
    generated_tokens = []
    planner_rounds = []
    latency_estimates = []
    for _, row in iter_jsonl(path):
        inference = row.get("inference")
        if not isinstance(inference, Mapping):
            continue
        if isinstance(inference.get("generated_tokens"), (int, float)):
            generated_tokens.append(float(inference["generated_tokens"]))
        elif isinstance(inference.get("final_generated_tokens"), (int, float)):
            generated_tokens.append(float(inference.get("draft_generated_tokens", 0)) + float(inference["final_generated_tokens"]))
        if isinstance(inference.get("planner_rounds"), (int, float)):
            planner_rounds.append(float(inference["planner_rounds"]))
        if isinstance(inference.get("latency_seconds"), (int, float)):
            latency_estimates.append(float(inference["latency_seconds"]))
        else:
            batch_seconds = inference.get("total_batch_seconds", inference.get("batch_seconds"))
            batch_size = inference.get("batch_size")
            if isinstance(batch_seconds, (int, float)) and isinstance(batch_size, (int, float)) and batch_size:
                latency_estimates.append(float(batch_seconds) / float(batch_size))
    return {
        "mean_generated_tokens": mean(generated_tokens) if generated_tokens else None,
        "mean_planner_rounds": mean(planner_rounds) if planner_rounds else 1.0,
        "mean_per_request_latency_seconds_estimate": mean(latency_estimates) if latency_estimates else None,
        "latency_is_batch_amortized_estimate": bool(latency_estimates),
    }


def compare_baselines(
    protocol_path: Path,
    conditions: Mapping[str, Tuple[Path, Path]],
    reference_id: str = "vaguehydro_lora",
) -> Dict[str, Any]:
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    gold_path = Path(protocol["manifest"])
    registry_path = Path(protocol["tool_registry"])
    if sha256_file(gold_path) != str(protocol["manifest_sha256"]).lower():
        raise ValueError("frozen manifest SHA256 does not match protocol")
    if sha256_file(registry_path) != str(protocol["tool_registry_sha256"]).lower():
        raise ValueError("ToolSpec registry SHA256 does not match protocol")
    registry = load_tool_registry(registry_path)
    rows: Dict[str, Any] = {}
    outcomes: Dict[str, Dict[str, Dict[str, int]]] = {}
    for condition_id, (prediction_path, report_path) in conditions.items():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        rows[condition_id] = {
            "prediction_path": str(prediction_path),
            "prediction_sha256": sha256_file(prediction_path),
            "report_path": str(report_path),
            "report_sha256": sha256_file(report_path),
            "metrics": {name: report["metrics"].get(name) for name in METRICS},
            "inference": _inference_summary(prediction_path),
        }
        outcomes[condition_id] = _binary_outcomes(gold_path, prediction_path, registry)

    significance: Dict[str, Any] = {}
    if reference_id in outcomes:
        reference = outcomes[reference_id]
        ids = sorted(reference)
        for condition_id, condition_outcomes in outcomes.items():
            if condition_id == reference_id:
                continue
            metric_results = {}
            for metric in ("schema", "action", "tool", "exact"):
                baseline = [condition_outcomes[query_id][metric] for query_id in ids]
                candidate = [reference[query_id][metric] for query_id in ids]
                metric_results[metric] = {
                    "paired_bootstrap": _paired_bootstrap(
                        baseline, candidate,
                        int(protocol["evaluation"]["bootstrap_samples"]),
                        int(protocol["evaluation"]["bootstrap_seed"]),
                    ),
                    "mcnemar_exact": _mcnemar_exact(baseline, candidate),
                }
            significance[f"{reference_id}_vs_{condition_id}"] = metric_results
    expected_ids = [str(item["id"]) for item in protocol["conditions"]]
    gold_count = sum(1 for _ in iter_jsonl(gold_path))
    return {
        "schema_version": "vague_hydro.multi_baseline_report.v1",
        "status": "complete" if set(expected_ids) <= set(rows) else "partial",
        "protocol_path": str(protocol_path),
        "protocol_sha256": sha256_file(protocol_path),
        "manifest_sha256": sha256_file(gold_path),
        "gold_count": gold_count,
        "condition_count": len(rows),
        "reference_condition": reference_id,
        "missing_conditions": sorted(set(expected_ids) - set(rows)),
        "conditions": rows,
        "paired_significance": significance,
    }
