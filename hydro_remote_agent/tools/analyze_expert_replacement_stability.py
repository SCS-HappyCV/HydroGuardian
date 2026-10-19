from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _rank(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        tied_rank = (cursor + end - 1) / 2.0
        for position in range(cursor, end):
            ranks[order[position]] = tied_rank
        cursor = end
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean, right_mean = fmean(left), fmean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_scale = math.sqrt(sum((value - left_mean) ** 2 for value in left))
    right_scale = math.sqrt(sum((value - right_mean) ** 2 for value in right))
    return None if left_scale == 0.0 or right_scale == 0.0 else numerator / (left_scale * right_scale)


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return _pearson(_rank(left), _rank(right))


def _score(row: Mapping[str, Any]) -> float:
    return float(row.get("task_score") or 0.0)


def _failure_flags(
    row: Mapping[str, Any], low_threshold: float, high_threshold: float
) -> dict[str, bool]:
    low = _score(row) < low_threshold
    return {
        "routing_exact_low_outcome": bool(row.get("routing_exact")) and low,
        "routing_wrong_high_outcome": not bool(row.get("routing_exact")) and _score(row) >= high_threshold,
        "execution_success_low_outcome": bool(row.get("execution_succeeded")) and low,
        "execution_failed": not bool(row.get("execution_succeeded")),
    }


def _load_condition(root: Path, condition: str, expected_count: int) -> dict[str, dict[str, Any]]:
    rows = load_jsonl(root / condition / "task_quality_rows.jsonl")
    by_id = {str(row["id"]): row for row in rows}
    if len(rows) != expected_count or len(by_id) != expected_count:
        raise ValueError(f"{condition}: expected {expected_count} unique rows, got {len(rows)}/{len(by_id)}")
    return by_id


def _stratified_deltas(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get(key, "unknown")), []).append(row)
    return {
        name: {
            "request_count": len(selected),
            "before_mean_task_score": fmean(float(row["before_score"]) for row in selected),
            "after_mean_task_score": fmean(float(row["after_score"]) for row in selected),
            "delta_mean_task_score": fmean(float(row["delta"]) for row in selected),
        }
        for name, selected in sorted(groups.items())
    }


def analyze(
    before_root: Path,
    after_root: Path,
    conditions: Sequence[str],
    expected_count: int = 240,
    low_threshold: float = 0.25,
    high_threshold: float = 0.5,
    before_label: str = "Pilot",
    after_label: str = "R007",
    before_integrity: str = "pilot_only_expert_test_leakage",
    after_integrity: str = "formal_r007_zero_test_overlap",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summaries: dict[str, Any] = {}
    transitions: list[dict[str, Any]] = []
    reference_ids: set[str] | None = None
    failure_names = (
        "routing_exact_low_outcome",
        "routing_wrong_high_outcome",
        "execution_success_low_outcome",
        "execution_failed",
    )

    for condition in conditions:
        before = _load_condition(before_root, condition, expected_count)
        after = _load_condition(after_root, condition, expected_count)
        if before.keys() != after.keys():
            raise ValueError(f"{condition}: before/after request populations differ")
        ids = set(before)
        if reference_ids is None:
            reference_ids = ids
        elif ids != reference_ids:
            raise ValueError(f"{condition}: request population differs across conditions")

        before_scores = [_score(before[request_id]) for request_id in sorted(ids)]
        after_scores = [_score(after[request_id]) for request_id in sorted(ids)]
        failure_transition_counts = {
            name: {"persisted": 0, "resolved": 0, "introduced": 0, "absent": 0}
            for name in failure_names
        }
        changed_count = 0
        for request_id in sorted(ids):
            old_row, new_row = before[request_id], after[request_id]
            old_score, new_score = _score(old_row), _score(new_row)
            if not math.isclose(old_score, new_score, rel_tol=0.0, abs_tol=1e-12):
                changed_count += 1
            old_flags = _failure_flags(old_row, low_threshold, high_threshold)
            new_flags = _failure_flags(new_row, low_threshold, high_threshold)
            for name in failure_names:
                state = (
                    "persisted" if old_flags[name] and new_flags[name]
                    else "resolved" if old_flags[name]
                    else "introduced" if new_flags[name]
                    else "absent"
                )
                failure_transition_counts[name][state] += 1
            transitions.append({
                "condition": condition,
                "id": request_id,
                "gold_action_type": new_row.get("gold_action_type"),
                "task_type": new_row.get("task_type"),
                "is_no_target": bool(new_row.get("metrics", {}).get("is_no_target")),
                "before_score": old_score,
                "after_score": new_score,
                "delta": new_score - old_score,
                "before_execution_succeeded": bool(old_row.get("execution_succeeded")),
                "after_execution_succeeded": bool(new_row.get("execution_succeeded")),
            })
        summaries[condition] = {
            "request_count": len(ids),
            "before_mean_task_score": fmean(before_scores),
            "after_mean_task_score": fmean(after_scores),
            "delta_mean_task_score": fmean(after_scores) - fmean(before_scores),
            "changed_request_count": changed_count,
            "request_level_before_after_spearman": spearman(before_scores, after_scores),
            "failure_transitions": failure_transition_counts,
        }

    for condition in conditions:
        selected = [row for row in transitions if row["condition"] == condition]
        summaries[condition]["stratified_score_delta"] = {
            "by_action_type": _stratified_deltas(selected, "gold_action_type"),
            "by_task_type": _stratified_deltas(selected, "task_type"),
            "by_no_target": _stratified_deltas(selected, "is_no_target"),
        }

    before_values = [summaries[name]["before_mean_task_score"] for name in conditions]
    after_values = [summaries[name]["after_mean_task_score"] for name in conditions]
    before_ranking = sorted(conditions, key=lambda name: (-summaries[name]["before_mean_task_score"], name))
    after_ranking = sorted(conditions, key=lambda name: (-summaries[name]["after_mean_task_score"], name))
    return ({
        "schema_version": "hydro_agent_bench.expert_replacement_stability.v1",
        "status": "complete",
        "before_label": before_label,
        "after_label": after_label,
        "before_integrity": before_integrity,
        "after_integrity": after_integrity,
        "expected_request_count": expected_count,
        "low_outcome_threshold": low_threshold,
        "high_outcome_threshold": high_threshold,
        "condition_count": len(conditions),
        "conditions": summaries,
        "ranking_stability": {
            "before_ranking": before_ranking,
            "after_ranking": after_ranking,
            "spearman": spearman(before_values, after_values),
            "top1_preserved": before_ranking[0] == after_ranking[0],
        },
    }, transitions)


def write_markdown(report: Mapping[str, Any], path: Path) -> None:
    stability = report["ranking_stability"]
    before_label = str(report.get("before_label", "Before"))
    after_label = str(report.get("after_label", "After"))
    lines = [
        f"# {before_label}-to-{after_label} Expert-Replacement Stability",
        "",
        f"> Before: {before_label} (`{report['before_integrity']}`); "
        f"after: {after_label} (`{report['after_integrity']}`).",
        "",
        f"Agent-ranking Spearman: `{stability['spearman']}`; top-1 preserved: `{stability['top1_preserved']}`.",
        "",
        f"| Condition | {before_label} outcome | {after_label} outcome | Delta | Changed requests | Request-level rho |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, summary in report["conditions"].items():
        rho = summary["request_level_before_after_spearman"]
        rho_text = "NA" if rho is None else f"{rho:.4f}"
        lines.append(
            f"| {name} | {summary['before_mean_task_score']:.4f} | "
            f"{summary['after_mean_task_score']:.4f} | {summary['delta_mean_task_score']:+.4f} | "
            f"{summary['changed_request_count']} | {rho_text} |"
        )
    lines.extend([
        "",
        f"{before_label} ranking: `{' > '.join(stability['before_ranking'])}`.",
        "",
        f"{after_label} ranking: `{' > '.join(stability['after_ranking'])}`.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Agent ranking stability under controlled expert replacement.")
    parser.add_argument("--before-root", type=Path, required=True)
    parser.add_argument("--after-root", type=Path, required=True)
    parser.add_argument("--condition", action="append", dest="conditions", required=True)
    parser.add_argument("--expected-count", type=int, default=240)
    parser.add_argument("--low-outcome-threshold", type=float, default=0.25)
    parser.add_argument("--high-outcome-threshold", type=float, default=0.5)
    parser.add_argument("--before-label", default="Pilot")
    parser.add_argument("--after-label", default="R007")
    parser.add_argument("--before-integrity", default="pilot_only_expert_test_leakage")
    parser.add_argument("--after-integrity", default="formal_r007_zero_test_overlap")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--transitions-csv", type=Path, required=True)
    args = parser.parse_args()
    report, transitions = analyze(
        args.before_root.resolve(), args.after_root.resolve(), args.conditions,
        expected_count=args.expected_count,
        low_threshold=args.low_outcome_threshold,
        high_threshold=args.high_outcome_threshold,
        before_label=args.before_label,
        after_label=args.after_label,
        before_integrity=args.before_integrity,
        after_integrity=args.after_integrity,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, args.markdown)
    with args.transitions_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(transitions[0]))
        writer.writeheader()
        writer.writerows(transitions)
    print(json.dumps({"status": "complete", "ranking_spearman": report["ranking_stability"]["spearman"]}))


if __name__ == "__main__":
    main()
