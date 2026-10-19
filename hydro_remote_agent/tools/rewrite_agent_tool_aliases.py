from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json
from hydro_remote_agent.evaluation.routing import iter_jsonl, parse_json_response
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tool_aliases import (
    execution_request_with_aliases as _execution_request_with_aliases,
    parse_tool_aliases as _parse_tool_aliases,
)


def rewrite_predictions(
    path: Path,
    registry,
    aliases: Mapping[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    transitions: Counter[str] = Counter()
    changed_rows = 0
    for _, source_row in iter_jsonl(path):
        row = copy.deepcopy(dict(source_row))
        request = parse_json_response(row.get("prediction"))
        rewritten = _execution_request_with_aliases(request, aliases, registry)
        changed = rewritten != request
        if changed:
            changed_rows += 1
            for source, target in aliases.items():
                before = canonical_json(request).count(f'"tool":"{source}"')
                after = canonical_json(rewritten).count(f'"tool":"{target}"')
                count = min(before, after)
                if count:
                    transitions[f"{source} -> {target}"] += count
        row["prediction"] = canonical_json(rewritten)
        row["tool_alias_rewrite"] = {
            "schema_version": "agent.tool_alias_rewrite.v1",
            "changed": changed,
            "aliases": dict(aliases),
        }
        rows.append(row)
    report = {
        "schema_version": "agent.tool_alias_rewrite_report.v1",
        "prediction_count": len(rows),
        "changed_prediction_count": changed_rows,
        "transition_counts": dict(sorted(transitions.items())),
        "aliases": dict(sorted(aliases.items())),
    }
    return rows, report


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rewrite AgentRequest tools through audited aliases.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--changed-output", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--tool-alias", action="append", required=True, metavar="SOURCE=TARGET")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    registry = load_tool_registry(args.registry)
    aliases = _parse_tool_aliases(args.tool_alias, registry)
    rows, report = rewrite_predictions(args.input, registry, aliases)
    write_jsonl(args.output, rows)
    if args.changed_output is not None:
        write_jsonl(
            args.changed_output,
            [row for row in rows if row["tool_alias_rewrite"]["changed"]],
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
