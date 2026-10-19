from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json
from hydro_remote_agent.capability_policy import apply_capability_policy, load_capability_policy
from hydro_remote_agent.evaluation.routing import iter_jsonl, parse_json_response
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


def apply_policy_rows(path: Path, policy, registry) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    changed_rows = []
    rule_counts: Counter[str] = Counter()
    for _, source_row in iter_jsonl(path):
        row = copy.deepcopy(dict(source_row))
        request = parse_json_response(row.get("prediction"))
        rewritten, decisions = apply_capability_policy(request, policy, registry)
        changed = rewritten != request
        for decision in decisions:
            rule_counts[str(decision["rule_id"])] += 1
        row["prediction"] = canonical_json(rewritten)
        row["capability_policy"] = {
            "schema_version": "cmge.capability_policy_application.v1",
            "policy_id": policy.policy_id,
            "changed": changed,
            "decisions": decisions,
        }
        rows.append(row)
        if changed:
            changed_rows.append(row)
    report = {
        "schema_version": "cmge.capability_policy_application_report.v1",
        "policy_id": policy.policy_id,
        "prediction_count": len(rows),
        "changed_prediction_count": len(changed_rows),
        "rule_application_counts": dict(sorted(rule_counts.items())),
    }
    return rows, report


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply an audited capability policy to AgentRequests.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--changed-output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    registry = load_tool_registry(args.registry)
    policy = load_capability_policy(args.policy, registry)
    rows, report = apply_policy_rows(args.input, policy, registry)
    _write_jsonl(args.output, rows)
    _write_jsonl(args.changed_output, [row for row in rows if row["capability_policy"]["changed"]])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
