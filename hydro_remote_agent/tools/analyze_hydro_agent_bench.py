from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def mean(values: Iterable[float]) -> float | None:
    selected = list(values)
    return fmean(selected) if selected else None


def rank(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        average_rank = (cursor + end - 1) / 2.0
        for position in range(cursor, end):
            result[order[position]] = average_rank
        cursor = end
    return result


def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = fmean(left)
    right_mean = fmean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_scale = math.sqrt(sum((value - left_mean) ** 2 for value in left))
    right_scale = math.sqrt(sum((value - right_mean) ** 2 for value in right))
    if left_scale == 0.0 or right_scale == 0.0:
        return None
    return numerator / (left_scale * right_scale)


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return pearson(rank(left), rank(right))


def stratified_bootstrap_ci(
    rows: Sequence[Mapping[str, Any]],
    value: Callable[[Mapping[str, Any]], float],
    samples: int,
    confidence: float,
    seed: int,
    stratum: str = "gold_action_type",
) -> dict[str, float | int | None]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(stratum, "unknown"))].append(row)
    estimate = mean(value(row) for row in rows)
    if not rows or samples <= 0:
        return {"estimate": estimate, "lower": None, "upper": None, "samples": 0}
    rng = np.random.default_rng(seed)
    draw_sums = np.zeros(samples, dtype=np.float64)
    for group in groups.values():
        values = np.asarray([value(row) for row in group], dtype=np.float64)
        draw_sums += rng.choice(values, size=(samples, len(values)), replace=True).sum(axis=1)
    draws = np.sort(draw_sums / len(rows))
    tail = (1.0 - confidence) / 2.0
    lower_index = max(0, min(samples - 1, int(math.floor(tail * samples))))
    upper_index = max(0, min(samples - 1, int(math.ceil((1.0 - tail) * samples)) - 1))
    return {
        "estimate": estimate,
        "lower": float(draws[lower_index]),
        "upper": float(draws[upper_index]),
        "samples": samples,
    }


def summarize_rows(
    rows: Sequence[Mapping[str, Any]], stats: Mapping[str, Any], include_ci: bool = True
) -> dict[str, Any]:
    samples = int(stats["bootstrap_samples"]) if include_ci else 0
    confidence = float(stats["confidence_level"])
    seed = int(stats.get("seed", 20260820))
    low_threshold = float(stats["low_outcome_threshold"])
    high_threshold = float(stats["high_outcome_threshold"])

    routing = lambda row: float(bool(row.get("routing_exact")))
    execution = lambda row: float(bool(row.get("execution_succeeded")))
    outcome = lambda row: float(row.get("task_score") or 0.0)
    route_ci = stratified_bootstrap_ci(rows, routing, samples, confidence, seed)
    execution_ci = stratified_bootstrap_ci(rows, execution, samples, confidence, seed + 1)
    outcome_ci = stratified_bootstrap_ci(rows, outcome, samples, confidence, seed + 2)
    route_values = [routing(row) for row in rows]
    execution_values = [execution(row) for row in rows]
    outcome_values = [outcome(row) for row in rows]
    route_exact_low = [row for row in rows if routing(row) == 1.0 and outcome(row) < low_threshold]
    route_wrong_high = [row for row in rows if routing(row) == 0.0 and outcome(row) >= high_threshold]
    execution_low = [row for row in rows if execution(row) == 1.0 and outcome(row) < low_threshold]
    return {
        "request_count": len(rows),
        "routing_exact": route_ci,
        "execution_success": execution_ci,
        "task_outcome": outcome_ci,
        "stage_gaps": {
            "routing_minus_outcome": route_ci["estimate"] - outcome_ci["estimate"],
            "execution_minus_outcome": execution_ci["estimate"] - outcome_ci["estimate"],
        },
        "request_level_correlations": {
            "routing_vs_outcome_spearman": spearman(route_values, outcome_values),
            "execution_vs_outcome_spearman": spearman(execution_values, outcome_values),
        },
        "disagreements": {
            "routing_exact_low_outcome_count": len(route_exact_low),
            "routing_exact_low_outcome_rate": len(route_exact_low) / len(rows) if rows else None,
            "routing_wrong_high_outcome_count": len(route_wrong_high),
            "routing_wrong_high_outcome_rate": len(route_wrong_high) / len(rows) if rows else None,
            "execution_success_low_outcome_count": len(execution_low),
            "execution_success_low_outcome_rate": len(execution_low) / len(rows) if rows else None,
        },
    }


def group_summary(
    rows: Sequence[Mapping[str, Any]], key: str, stats: Mapping[str, Any], include_ci: bool = False
) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key, "unknown"))].append(row)
    return {
        name: summarize_rows(selected, stats, include_ci=include_ci)
        for name, selected in sorted(groups.items())
    }


def no_target_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    dense = [row for row in rows if row.get("score_kind") == "binary_mask"]
    pairs = [
        (bool(row.get("metrics", {}).get("is_no_target")), bool(row.get("metrics", {}).get("predicted_no_target")))
        for row in dense
    ]
    true_positive = sum(gold and predicted for gold, predicted in pairs)
    false_positive = sum(not gold and predicted for gold, predicted in pairs)
    false_negative = sum(gold and not predicted for gold, predicted in pairs)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else None
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {
        "dense_request_count": len(pairs),
        "gold_no_target_count": sum(gold for gold, _ in pairs),
        "predicted_no_target_count": sum(predicted for _, predicted in pairs),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def analyze(config_path: Path, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    config = load_json(config_path)
    stats = dict(config["statistics"])
    stats["seed"] = int(config["seed"])
    root = project_root / config["task_rows_root"]
    expected_count = int(config["population"]["request_count"])
    rows_by_condition: dict[str, list[dict[str, Any]]] = {}
    expected_ids: set[str] | None = None
    for condition in config["conditions"]:
        path = root / condition / "task_quality_rows.jsonl"
        rows = load_jsonl(path)
        ids = {str(row["id"]) for row in rows}
        if len(rows) != expected_count or len(ids) != expected_count:
            raise ValueError(f"{condition}: expected {expected_count} unique requests, got {len(rows)} rows/{len(ids)} ids")
        if expected_ids is None:
            expected_ids = ids
        elif ids != expected_ids:
            raise ValueError(f"{condition}: request population differs from the frozen population")
        rows_by_condition[condition] = rows

    conditions: dict[str, Any] = {}
    for condition, rows in rows_by_condition.items():
        conditions[condition] = {
            "overall": summarize_rows(rows, stats),
            "by_action_type": group_summary(rows, "gold_action_type", stats, include_ci=True),
            "by_task_type": group_summary(rows, "task_type", stats),
            "by_ambiguity_level": group_summary(rows, "ambiguity_level", stats),
            "by_language": group_summary(rows, "language", stats),
            "no_target": no_target_metrics(rows),
        }

    learned = config["learned_conditions"]
    proxy_vectors = {
        "routing_exact": [conditions[name]["overall"]["routing_exact"]["estimate"] for name in learned],
        "execution_success": [conditions[name]["overall"]["execution_success"]["estimate"] for name in learned],
        "task_outcome": [conditions[name]["overall"]["task_outcome"]["estimate"] for name in learned],
    }
    rankings = {
        metric: sorted(zip(learned, values), key=lambda item: (-item[1], item[0]))
        for metric, values in proxy_vectors.items()
    }
    rank_agreement = {
        "routing_vs_outcome_spearman": spearman(proxy_vectors["routing_exact"], proxy_vectors["task_outcome"]),
        "execution_vs_outcome_spearman": spearman(proxy_vectors["execution_success"], proxy_vectors["task_outcome"]),
    }
    formal_eligible = bool(config.get("data_integrity", {}).get("formal_outcome_eligible", True))
    return {
        "schema_version": "hydro_agent_bench.analysis.v1",
        "protocol_id": config["protocol_id"],
        "status": "formal_complete" if formal_eligible else "pilot_complete_formal_blocked_by_expert_leakage",
        "conditions": conditions,
        "condition_rankings": rankings,
        "agent_level_rank_agreement": rank_agreement,
        "independent_expert_replacement": config["independent_expert_replacement"],
        "data_integrity": config.get("data_integrity", {}),
        "limitations": list(config["scope"]["excluded"]),
    }


def write_markdown(report: Mapping[str, Any], path: Path) -> None:
    lines = [
        "# HydroAgentBench v1 Formal Analysis",
        "",
        f"Protocol: `{report['protocol_id']}`",
        f"Status: `{report['status']}`",
        "",
        "## Three-stage results",
        "",
        "| Condition | Routing exact | Execution | Task outcome | Exec-outcome gap |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, condition in report["conditions"].items():
        overall = condition["overall"]
        lines.append(
            f"| {name} | {overall['routing_exact']['estimate']:.4f} | "
            f"{overall['execution_success']['estimate']:.4f} | {overall['task_outcome']['estimate']:.4f} | "
            f"{overall['stage_gaps']['execution_minus_outcome']:.4f} |"
        )
    lines.extend([
        "",
        "## Agent-level rank agreement",
        "",
        f"- Routing exact vs outcome Spearman: `{report['agent_level_rank_agreement']['routing_vs_outcome_spearman']}`",
        f"- Execution success vs outcome Spearman: `{report['agent_level_rank_agreement']['execution_vs_outcome_spearman']}`",
        "",
        "## Scope",
        "",
    ])
    lines.extend(f"- Not claimed: {item}" for item in report["limitations"])
    if report.get("data_integrity", {}).get("formal_outcome_eligible", True):
        integrity_note = (
            "This analysis is formal-outcome eligible under the declared data-integrity protocol."
        )
    else:
        integrity_note = (
            "The current population analysis is pilot evidence only. Formal outcome tables require "
            "experts retrained on the frozen split."
        )
    lines.extend(["", integrity_note, ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze HydroAgentBench with outcome-aware three-stage metrics.")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "hydro_remote_agent/configs/hydro_agent_bench_protocol_v1.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "runs/hydro_remote_agent/hydro_agent_bench_v1/formal_analysis.json")
    parser.add_argument("--markdown", type=Path, default=PROJECT_ROOT / "runs/hydro_remote_agent/hydro_agent_bench_v1/FORMAL_ANALYSIS.md")
    args = parser.parse_args()
    report = analyze(args.config.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, args.markdown)
    print(json.dumps({"status": report["status"], "output": str(args.output), "markdown": str(args.markdown)}))


if __name__ == "__main__":
    main()
