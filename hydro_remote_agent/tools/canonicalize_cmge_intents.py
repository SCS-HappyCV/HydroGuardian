from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from hydro_remote_agent.cmge_planner import canonicalize_cmge_plan
from hydro_remote_agent.evaluation.routing import iter_jsonl, parse_json_response


def canonicalize_predictions(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    transitions: Counter[str] = Counter()
    changed_plans = 0
    changed_claims = 0
    for _, row in iter_jsonl(path):
        output = dict(row)
        plan = parse_json_response(row.get("prediction"))
        normalized, changes = canonicalize_cmge_plan(plan)
        if changes:
            changed_plans += 1
            changed_claims += len(changes)
            for change in changes:
                transitions[f"{change['source_intent']} -> {change['target_intent']}"] += 1
        output["prediction"] = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        output["intent_canonicalization"] = {
            "schema_version": "cmge.intent_canonicalization.v1",
            "changes": changes,
        }
        rows.append(output)
    report = {
        "schema_version": "cmge.intent_canonicalization_report.v1",
        "prediction_count": len(rows),
        "changed_plan_count": changed_plans,
        "changed_claim_count": changed_claims,
        "transition_counts": dict(sorted(transitions.items())),
    }
    return rows, report


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Canonicalize non-standard CMGE intent labels.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    rows, report = canonicalize_predictions(args.input)
    write_jsonl(args.output, rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
