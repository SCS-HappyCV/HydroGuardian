from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from hydro_remote_agent.evaluation.routing import (
    canonical_json,
    extract_gold,
    iter_jsonl,
    parse_json_response,
    sha256_file,
)


E2E_COMPARISON_SCHEMA_VERSION = "vague_hydro.e2e_comparison.v1"
DEFAULT_ACTION_COUNTS = {"direct_answer": 10, "tool_call": 20, "workflow": 20}


def _action_type(record: Mapping[str, Any]) -> str:
    _, request, _ = extract_gold(record)
    action = request.get("action")
    return str(action.get("type", "")) if isinstance(action, Mapping) else ""


def _stable_seed(seed: int, *parts: str) -> int:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).digest()
    return seed ^ int.from_bytes(digest[:8], "big")


def freeze_stratified_subset(
    records: Sequence[Mapping[str, Any]],
    action_counts: Mapping[str, int] = DEFAULT_ACTION_COUNTS,
    seed: int = 20260808,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Freeze action quotas while balancing language and ambiguity level."""
    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for raw_record in records:
        record = dict(raw_record)
        key = (
            _action_type(record),
            str(record.get("language", "unknown")),
            str(record.get("ambiguity_level", "unknown")),
        )
        groups[key].append(record)

    languages = sorted({key[1] for key in groups})
    levels = sorted({key[2] for key in groups})
    if not languages or not levels:
        raise ValueError("subset source has no language/ambiguity strata")

    selected: List[Dict[str, Any]] = []
    quota_rows: List[Dict[str, Any]] = []
    for action_index, (action, count) in enumerate(action_counts.items()):
        if count < 0:
            raise ValueError(f"negative quota for action {action!r}")
        language_base, language_extra = divmod(count, len(languages))
        language_order = list(languages)
        random.Random(_stable_seed(seed, action, "languages")).shuffle(language_order)
        language_quotas = {language: language_base for language in languages}
        for language in language_order[:language_extra]:
            language_quotas[language] += 1

        for language_index, language in enumerate(languages):
            language_count = language_quotas[language]
            level_base, level_extra = divmod(language_count, len(levels))
            offset = (action_index + language_index) % len(levels)
            level_order = levels[offset:] + levels[:offset]
            for level_index, level in enumerate(level_order):
                quota = level_base + int(level_index < level_extra)
                candidates = list(groups.get((action, language, level), ()))
                random.Random(
                    _stable_seed(seed, action, language, level)
                ).shuffle(candidates)
                if len(candidates) < quota:
                    raise ValueError(
                        f"stratum {(action, language, level)!r} has "
                        f"{len(candidates)} records but needs {quota}"
                    )
                selected.extend(candidates[:quota])
                quota_rows.append({
                    "action_type": action,
                    "language": language,
                    "ambiguity_level": level,
                    "quota": quota,
                    "available": len(candidates),
                })

    random.Random(seed).shuffle(selected)
    ids = [str(record.get("id", "")) for record in selected]
    sample_ids = [str(record.get("sample_id", "")) for record in selected]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("selected records contain missing or duplicate IDs")
    if not all(sample_ids) or len(sample_ids) != len(set(sample_ids)):
        raise ValueError("selected records contain missing or duplicate sample IDs")

    observed = Counter(
        (
            _action_type(record),
            str(record.get("language", "unknown")),
            str(record.get("ambiguity_level", "unknown")),
        )
        for record in selected
    )
    report = {
        "schema_version": E2E_COMPARISON_SCHEMA_VERSION,
        "status": "frozen",
        "seed": seed,
        "source_count": len(records),
        "selected_count": len(selected),
        "requested_action_counts": dict(action_counts),
        "observed_action_counts": dict(Counter(_action_type(row) for row in selected)),
        "observed_language_counts": dict(Counter(str(row["language"]) for row in selected)),
        "observed_ambiguity_counts": dict(
            Counter(str(row["ambiguity_level"]) for row in selected)
        ),
        "strata": [
            {**row, "selected": observed[(row["action_type"], row["language"], row["ambiguity_level"])]}
            for row in quota_rows
        ],
        "request_ids": ids,
    }
    return selected, report


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _latency(values: Sequence[float]) -> Dict[str, float | None]:
    return {
        "mean_ms": sum(values) / len(values) if values else None,
        "p50_ms": _quantile(values, 0.50),
        "p95_ms": _quantile(values, 0.95),
    }


def _verifier_accepted(execution: Mapping[str, Any]) -> bool:
    if execution.get("status") != "succeeded":
        return False
    result = execution.get("result")
    if not isinstance(result, Mapping):
        return False
    workflow = result.get("workflow_result")
    if not isinstance(workflow, Mapping):
        return True
    for step in workflow.get("steps", []):
        if not isinstance(step, Mapping):
            continue
        verification = step.get("verification_result")
        if isinstance(verification, Mapping) and verification.get("status") != "succeeded":
            return False
    return True


def summarize_e2e_condition(
    gold_path: Path,
    run_path: Path,
    condition: str,
) -> Dict[str, Any]:
    gold = {extract_gold(row)[0]: extract_gold(row)[1] for _, row in iter_jsonl(gold_path)}
    runs = {str(row.get("id", "")): row for _, row in iter_jsonl(run_path)}
    if set(runs) != set(gold):
        raise ValueError(
            f"condition {condition!r} population mismatch: "
            f"missing={sorted(set(gold) - set(runs))[:5]} "
            f"extra={sorted(set(runs) - set(gold))[:5]}"
        )

    planner_ms: List[float] = []
    execution_ms: List[float] = []
    total_ms: List[float] = []
    exact_count = 0
    execution_success = 0
    verified_success = 0
    e2e_correct = 0
    tool_invocations = 0
    rows = []
    for request_id, gold_request in gold.items():
        run = runs[request_id]
        prediction = None
        try:
            prediction = parse_json_response(run.get("prediction"))
        except Exception:
            pass
        exact = prediction is not None and canonical_json(prediction) == canonical_json(gold_request)
        execution = run.get("execution")
        succeeded = isinstance(execution, Mapping) and execution.get("status") == "succeeded"
        verified = isinstance(execution, Mapping) and _verifier_accepted(execution)
        protocol_correct = bool(exact and verified)
        exact_count += int(exact)
        execution_success += int(succeeded)
        verified_success += int(verified)
        e2e_correct += int(protocol_correct)
        timing = run.get("timing", {})
        if isinstance(timing, Mapping):
            planner_ms.append(float(timing.get("planner_ms", 0.0)))
            execution_ms.append(float(timing.get("execution_ms", 0.0)))
            total_ms.append(float(timing.get("total_ms", 0.0)))
        count = int(run.get("expert_invocation_count", 0))
        tool_invocations += count
        rows.append({
            "id": request_id,
            "routing_exact": exact,
            "execution_succeeded": succeeded,
            "verifier_accepted": verified,
            "verified_e2e_correct": protocol_correct,
            "expert_invocation_count": count,
        })

    count = len(gold)
    return {
        "condition": condition,
        "request_count": count,
        "routing_exact_rate": exact_count / count,
        "execution_success_rate": execution_success / count,
        "verifier_acceptance_rate": verified_success / count,
        "verified_e2e_correct_rate": e2e_correct / count,
        "verified_e2e_correct_definition": (
            "final AgentRequest exact match AND real execution succeeded AND all invoked verifiers succeeded"
        ),
        "task_output_correctness_available": False,
        "task_output_correctness_note": (
            "The mixed request set has no single common point/pixel-level target metric; "
            "execution completion is not reported as mask correctness."
        ),
        "expert_invocation_count": tool_invocations,
        "expert_invocations_per_request": tool_invocations / count,
        "latency": {
            "planner": _latency(planner_ms),
            "execution": _latency(execution_ms),
            "total_wall_clock": _latency(total_ms),
        },
        "requests": rows,
    }


def compare_e2e_conditions(
    gold_path: Path,
    condition_paths: Mapping[str, Path],
    reference_condition: Optional[str] = None,
) -> Dict[str, Any]:
    conditions = {
        name: summarize_e2e_condition(gold_path, path, name)
        for name, path in condition_paths.items()
    }
    report = {
        "schema_version": E2E_COMPARISON_SCHEMA_VERSION,
        "status": "completed",
        "condition_count": len(conditions),
        "gold_count": next(iter(conditions.values()))["request_count"] if conditions else 0,
        "gold_path": str(gold_path),
        "gold_sha256": sha256_file(gold_path),
        "conditions": conditions,
        "run_sha256": {name: sha256_file(path) for name, path in condition_paths.items()},
    }
    if len(conditions) >= 2:
        reference_name = reference_condition
        if reference_name is None:
            reference_name = (
                "vaguehydro_lora"
                if "vaguehydro_lora" in conditions
                else next(iter(conditions))
            )
        if reference_name not in conditions:
            raise ValueError(f"Unknown reference condition {reference_name!r}")
        reference_rows = {
            row["id"]: row for row in conditions[reference_name]["requests"]
        }
        comparisons: Dict[str, Any] = {}
        for baseline_name in conditions:
            if baseline_name == reference_name:
                continue
            baseline_rows = {
                row["id"]: row for row in conditions[baseline_name]["requests"]
            }
            significance: Dict[str, Any] = {
                "baseline": baseline_name,
                "candidate": reference_name,
            }
            for metric in (
                "routing_exact",
                "execution_succeeded",
                "verified_e2e_correct",
            ):
                significance[metric] = _paired_binary_significance(
                    [int(baseline_rows[request_id][metric]) for request_id in reference_rows],
                    [int(reference_rows[request_id][metric]) for request_id in reference_rows],
                    samples=10000,
                    seed=20260808,
                )
            comparisons[baseline_name] = significance
        report["reference_condition"] = reference_name
        report["paired_significance_by_baseline"] = comparisons
        if len(comparisons) == 1:
            report["paired_significance"] = next(iter(comparisons.values()))
    return report


def _paired_binary_significance(
    baseline: Sequence[int],
    candidate: Sequence[int],
    samples: int,
    seed: int,
) -> Dict[str, Any]:
    if len(baseline) != len(candidate) or not baseline:
        raise ValueError("paired significance requires equal non-empty populations")
    differences = [candidate_value - baseline_value for baseline_value, candidate_value in zip(baseline, candidate)]
    rng = random.Random(seed)
    deltas = []
    for _ in range(samples):
        deltas.append(sum(differences[rng.randrange(len(differences))] for _ in differences) / len(differences))
    deltas.sort()
    improved = sum(int(value == 1) for value in differences)
    regressed = sum(int(value == -1) for value in differences)
    discordant = improved + regressed
    if discordant:
        tail = sum(math.comb(discordant, index) for index in range(min(improved, regressed) + 1))
        p_value = min(1.0, 2.0 * tail / (2 ** discordant))
    else:
        p_value = 1.0
    return {
        "delta": sum(differences) / len(differences),
        "paired_bootstrap_95_ci": {
            "lower": deltas[int(samples * 0.025)],
            "upper": deltas[min(int(samples * 0.975), samples - 1)],
            "samples": samples,
            "seed": seed,
        },
        "mcnemar_exact": {
            "improved": improved,
            "regressed": regressed,
            "p_value_two_sided": p_value,
        },
    }
