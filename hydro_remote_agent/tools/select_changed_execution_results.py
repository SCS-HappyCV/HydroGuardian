from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from hydro_remote_agent.evaluation.routing import extract_prediction, iter_jsonl


def _is_changed(row: Mapping[str, Any]) -> bool:
    return any(
        isinstance(row.get(marker), Mapping) and row[marker].get("changed") is True
        for marker in ("tool_alias_rewrite", "capability_policy")
    )


def select_results(predictions: Path, results: Path, output: Path) -> dict[str, Any]:
    required = {
        extract_prediction(row)[0]
        for _, row in iter_jsonl(predictions)
        if _is_changed(row)
    }
    available = {
        str(row.get("id", "")): dict(row)
        for _, row in iter_jsonl(results)
        if row.get("id")
    }
    missing = sorted(required - set(available))
    if missing:
        raise ValueError(f"Missing changed execution results: {missing[:5]}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row_id in sorted(required):
            handle.write(json.dumps(available[row_id], ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "schema_version": "agent.changed_execution_selection.v1",
        "required_count": len(required),
        "source_result_count": len(available),
        "selected_count": len(required),
        "ignored_source_count": len(available) - len(required),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select real execution rows required by changed predictions.")
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = select_results(args.predictions, args.results, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
