from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable


ACTION_ORDER = ("direct_answer", "tool_call", "workflow")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    return fmean(materialized) if materialized else None


def _rank(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        average_rank = (cursor + 1 + end) / 2.0
        for position in range(cursor, end):
            ranks[indexed[position][0]] = average_rank
        cursor = end
    return ranks


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = fmean(left)
    right_mean = fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_scale = sum((x - left_mean) ** 2 for x in left)
    right_scale = sum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_scale * right_scale)
    return numerator / denominator if denominator else None


def _spearman(left: list[float], right: list[float]) -> float | None:
    return _pearson(_rank(left), _rank(right))


def _local_rows_path(project_root: Path, report_path: Path, condition: str) -> Path:
    return report_path.parent / condition / "task_quality_rows.jsonl"


def _expert_request_id(query_id: str) -> str | None:
    core = query_id.split(":", 1)[-1].split(":dense", 1)[0]
    parts = core.split("-")
    if len(parts) < 5:
        return None
    sample_id = f"{parts[0]}_{parts[1]}"
    task_type = parts[2].replace("no-target", "no_target")
    return "_".join((sample_id, task_type, *parts[3:]))


def _ranked_condition_scores(scores: dict[str, float]) -> list[str]:
    return [name for name, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]


def _expert_configuration_replay(
    config: dict[str, Any],
    project_root: Path,
    rows_by_condition: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    configurations = config.get("expert_configurations", [])
    results: dict[str, Any] = {}
    score_vectors: dict[str, dict[str, float]] = {}
    for configuration in configurations:
        result_path = project_root / configuration["results"]
        if not result_path.exists():
            results[configuration["id"]] = {"available": False, "path": str(result_path)}
            continue
        expert_rows = _load_jsonl(result_path)
        expert_scores = {
            str(row["request_id"]): float(row.get("metrics", {}).get("iou", 0.0))
            for row in expert_rows
            if row.get("request_id")
        }
        condition_scores: dict[str, float] = {}
        matched = 0
        total = 0
        for condition in config["learned_agent_conditions"]:
            rows = [
                row
                for row in rows_by_condition.get(condition, [])
                if row.get("gold_action_type") == "tool_call"
                and row.get("score_kind") == "binary_mask"
            ]
            replayed: list[float] = []
            for row in rows:
                total += 1
                request_id = _expert_request_id(str(row["id"]))
                if request_id not in expert_scores:
                    continue
                matched += 1
                replayed.append(
                    expert_scores[request_id]
                    if row.get("routing_exact") and row.get("execution_succeeded")
                    else 0.0
                )
            if replayed:
                condition_scores[condition] = fmean(replayed)
        coverage = matched / total if total else 0.0
        score_vectors[configuration["id"]] = condition_scores
        results[configuration["id"]] = {
            "available": True,
            "path": str(result_path),
            "matched_rows": matched,
            "total_rows": total,
            "coverage": coverage,
            "condition_scores": condition_scores,
            "ranking": _ranked_condition_scores(condition_scores),
        }

    available_ids = [
        configuration["id"]
        for configuration in configurations
        if results.get(configuration["id"], {}).get("available")
    ]
    ranking_spearman = None
    if len(available_ids) >= 2:
        left = score_vectors[available_ids[0]]
        right = score_vectors[available_ids[1]]
        common = sorted(set(left) & set(right))
        ranking_spearman = _spearman(
            [left[name] for name in common], [right[name] for name in common]
        )
    minimum_coverage = config["thresholds"]["minimum_expert_replay_coverage"]
    minimum_spearman = config["thresholds"]["minimum_expert_ranking_spearman"]
    minimum_count = config["required_expert_configurations"]
    coverage_pass = all(
        results[item]["coverage"] >= minimum_coverage for item in available_ids
    )
    passed = bool(
        len(available_ids) >= minimum_count
        and coverage_pass
        and ranking_spearman is not None
        and ranking_spearman >= minimum_spearman
    )
    return {
        "available": len(available_ids) >= minimum_count,
        "configuration_count": len(available_ids),
        "required": minimum_count,
        "configurations": results,
        "ranking_spearman": ranking_spearman,
        "minimum_ranking_spearman": minimum_spearman,
        "minimum_coverage": minimum_coverage,
        "pass": passed,
        "scope": "Language-expert calibration replay; the formal study still requires an independent model replacement.",
    }


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored_rows = [row for row in rows if row.get("task_score") is not None]
    mask_rows = [
        row
        for row in scored_rows
        if row.get("score_kind") in {"binary_mask", "full_scene"}
    ]
    summary: dict[str, Any] = {
        "overall": {
            "request_count": len(rows),
            "routing_exact_rate": _mean(float(bool(row.get("routing_exact"))) for row in rows),
            "execution_success_rate": _mean(
                float(bool(row.get("execution_succeeded"))) for row in rows
            ),
            "mean_task_score": _mean(float(row["task_score"]) for row in scored_rows),
            "dense_artifact_score": _mean(float(row["task_score"]) for row in mask_rows),
        }
    }
    for action_type in ACTION_ORDER:
        selected = [row for row in rows if row.get("gold_action_type") == action_type]
        scored = [row for row in selected if row.get("task_score") is not None]
        summary[action_type] = {
            "request_count": len(selected),
            "scored_count": len(scored),
            "routing_exact_rate": _mean(float(bool(row.get("routing_exact"))) for row in selected),
            "execution_success_rate": _mean(
                float(bool(row.get("execution_succeeded"))) for row in selected
            ),
            "mean_task_score": _mean(float(row["task_score"]) for row in scored),
        }
    return summary


def analyze(config_path: Path, project_root: Path) -> dict[str, Any]:
    config = _load_json(config_path)
    report_path = project_root / config["task_quality_report"]
    report = _load_json(report_path)
    rows_by_condition: dict[str, list[dict[str, Any]]] = {}
    missing_conditions: list[str] = []
    summaries: dict[str, Any] = {}

    for condition in config["conditions"]:
        rows_path = _local_rows_path(project_root, report_path, condition)
        if not rows_path.exists():
            missing_conditions.append(condition)
            continue
        rows = _load_jsonl(rows_path)
        rows_by_condition[condition] = rows
        summaries[condition] = _summarize_rows(rows)

    thresholds = config["thresholds"]
    reference = config["reference_condition"]
    reference_summary = summaries.get(reference, {})
    single = reference_summary.get("tool_call", {})
    workflow = reference_summary.get("workflow", {})
    single_score = single.get("mean_task_score")
    workflow_score = workflow.get("mean_task_score")
    workflow_execution = workflow.get("execution_success_rate")

    depth_support = all(
        value is not None
        for value in (
            single_score,
            workflow_score,
            single.get("routing_exact_rate"),
            workflow.get("routing_exact_rate"),
        )
    )
    depth_pass = bool(
        depth_support
        and single["routing_exact_rate"] >= thresholds["minimum_reference_routing_rate"]
        and workflow["routing_exact_rate"] >= thresholds["minimum_reference_routing_rate"]
        and single_score - workflow_score
        >= thresholds["minimum_single_to_workflow_score_drop"]
    )
    execution_gap = (
        workflow_execution - workflow_score
        if workflow_execution is not None and workflow_score is not None
        else None
    )
    execution_gap_pass = bool(
        execution_gap is not None
        and execution_gap >= thresholds["minimum_workflow_execution_to_outcome_gap"]
    )

    pooled_routing: list[float] = []
    pooled_scores: list[float] = []
    pooled_counts: dict[str, int] = {}
    for condition in config["learned_agent_conditions"]:
        rows = rows_by_condition.get(condition, [])
        selected = [
            row
            for row in rows
            if row.get("gold_action_type") == "tool_call"
            and row.get("score_kind") == "binary_mask"
            and row.get("task_score") is not None
        ]
        pooled_counts[condition] = len(selected)
        pooled_routing.extend(float(bool(row.get("routing_exact"))) for row in selected)
        pooled_scores.extend(float(row["task_score"]) for row in selected)
    single_tool_spearman = _spearman(pooled_routing, pooled_scores)
    correlation_kill = bool(
        single_tool_spearman is not None
        and single_tool_spearman > thresholds["kill_single_tool_spearman"]
    )

    rule_condition = config["rule_condition"]
    rule_summary = summaries.get(rule_condition)
    available_agent_workflow_scores = {
        condition: condition_summary["workflow"]["mean_task_score"]
        for condition, condition_summary in summaries.items()
        if condition != config["oracle_condition"]
        and condition_summary["workflow"]["mean_task_score"] is not None
    }
    best_agent_workflow_score = (
        max(available_agent_workflow_scores.values())
        if available_agent_workflow_scores
        else None
    )
    rule_to_best_delta = None
    if rule_summary and best_agent_workflow_score is not None:
        rule_score = rule_summary["workflow"]["mean_task_score"]
        if rule_score is not None:
            rule_to_best_delta = best_agent_workflow_score - rule_score
    rule_kill = bool(
        rule_to_best_delta is not None
        and rule_to_best_delta < thresholds["kill_rule_to_best_workflow_delta"]
    )

    expert_replay = _expert_configuration_replay(config, project_root, rows_by_condition)
    expert_stability_available = expert_replay["available"]
    pending = []
    if rule_summary is None:
        pending.append("rule_router_task_quality")
    if not expert_stability_available:
        pending.append("second_expert_configuration")

    kill_reasons = []
    if correlation_kill:
        kill_reasons.append("single_tool_routing_is_near_sufficient_proxy")
    if rule_kill:
        kill_reasons.append("rule_router_matches_best_workflow_outcome")
    if not depth_pass:
        kill_reasons.append("no_preregistered_depth_gap")
    if not execution_gap_pass:
        kill_reasons.append("no_preregistered_execution_outcome_gap")
    if expert_stability_available and not expert_replay["pass"]:
        kill_reasons.append("agent_ranking_is_not_stable_across_expert_configurations")

    if kill_reasons:
        decision = "kill"
    elif pending:
        decision = "continue_pending_conditions"
    else:
        decision = "pass"

    return {
        "schema_version": "hydro_agent_bench.gate_report.v1",
        "decision": decision,
        "config_path": str(config_path),
        "task_quality_report": str(report_path),
        "condition_summaries": summaries,
        "missing_conditions": missing_conditions,
        "tests": {
            "reference_depth_gap": {
                "reference_condition": reference,
                "single_tool_score": single_score,
                "workflow_score": workflow_score,
                "single_minus_workflow": (
                    single_score - workflow_score
                    if single_score is not None and workflow_score is not None
                    else None
                ),
                "pass": depth_pass,
            },
            "workflow_execution_to_outcome_gap": {
                "execution_success_rate": workflow_execution,
                "task_score": workflow_score,
                "gap": execution_gap,
                "pass": execution_gap_pass,
            },
            "single_tool_routing_outcome_spearman": {
                "rho": single_tool_spearman,
                "row_counts": pooled_counts,
                "kill_threshold": thresholds["kill_single_tool_spearman"],
                "kill_triggered": correlation_kill,
            },
            "rule_to_best_workflow_delta": {
                "delta": rule_to_best_delta,
                "kill_threshold": thresholds["kill_rule_to_best_workflow_delta"],
                "kill_triggered": rule_kill,
            },
            "expert_configuration_stability": expert_replay,
        },
        "kill_reasons": kill_reasons,
        "pending_conditions": pending,
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    tests = report["tests"]
    depth = tests["reference_depth_gap"]
    execution = tests["workflow_execution_to_outcome_gap"]
    correlation = tests["single_tool_routing_outcome_spearman"]
    rule = tests["rule_to_best_workflow_delta"]
    expert = tests["expert_configuration_stability"]
    lines = [
        "# HydroAgentBench Gate Report",
        "",
        f"**Decision:** `{report['decision']}`",
        "",
        "## Preregistered Tests",
        "",
        "| Test | Result | Status |",
        "|---|---:|---|",
        f"| Single-tool minus workflow task score | {depth['single_minus_workflow']} | {'PASS' if depth['pass'] else 'FAIL'} |",
        f"| Workflow execution minus outcome | {execution['gap']} | {'PASS' if execution['pass'] else 'FAIL'} |",
        f"| Single-tool routing/outcome Spearman | {correlation['rho']} | {'KILL' if correlation['kill_triggered'] else 'PASS'} |",
        f"| Best agent minus rule-router workflow score | {rule['delta']} | {'KILL' if rule['kill_triggered'] else 'PENDING' if rule['delta'] is None else 'PASS'} |",
        f"| Expert-configuration ranking Spearman | {expert['ranking_spearman']} | {'PASS' if expert['pass'] else 'FAIL' if expert['available'] else 'PENDING'} |",
        "",
        "## Agent Conditions",
        "",
        "| Condition | Routing exact | Execution success | Mean task score | Dense artifact score |",
        "|---|---:|---:|---:|---:|",
    ]
    for condition, summary in report["condition_summaries"].items():
        overall = summary["overall"]
        lines.append(
            f"| {condition} | {overall['routing_exact_rate']:.4f} | "
            f"{overall['execution_success_rate']:.4f} | {overall['mean_task_score']:.4f} | "
            f"{overall['dense_artifact_score']:.4f} |"
        )
    lines.extend([
        "",
        "## Missing Conditions",
        "",
    ])
    if report["pending_conditions"]:
        lines.extend(f"- `{item}`" for item in report["pending_conditions"])
    else:
        lines.append("None.")
    lines.extend(["", "## Kill Reasons", ""])
    if report["kill_reasons"]:
        lines.extend(f"- `{item}`" for item in report["kill_reasons"])
    else:
        lines.append("None.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="hydro_remote_agent/configs/hydro_agent_bench_gate_v1.json",
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--output-dir",
        default="runs/hydro_remote_agent/hydro_agent_bench_gate_v1",
    )
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()
    config_path = (project_root / args.config).resolve()
    output_dir = (project_root / args.output_dir).resolve()
    report = analyze(config_path, project_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "gate_report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=True, indent=2)
        handle.write("\n")
    _write_markdown(report, output_dir / "HYDRO_AGENT_BENCH_GATE_REPORT.md")
    print(json.dumps({"decision": report["decision"], "output_dir": str(output_dir)}))


if __name__ == "__main__":
    main()
