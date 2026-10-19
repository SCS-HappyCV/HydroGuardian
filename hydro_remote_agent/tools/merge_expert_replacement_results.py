from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from hydro_remote_agent.evaluation.execution import summarize_execution
from hydro_remote_agent.evaluation.routing import extract_prediction, iter_jsonl


def _latest_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for _, row in iter_jsonl(path):
        row_id = str(row.get("id", ""))
        if not row_id:
            raise ValueError(f"Execution row in {path} is missing id")
        rows[row_id] = dict(row)
    return rows


def merge_expert_replacement_results(
    prediction_path: Path,
    base_result_path: Path,
    replacement_result_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    prediction_rows = [dict(row) for _, row in iter_jsonl(prediction_path)]
    prediction_ids = [extract_prediction(row)[0] for row in prediction_rows]
    if len(prediction_ids) != len(set(prediction_ids)):
        raise ValueError("Prediction file contains duplicate request IDs")

    changed_ids = {
        str(row["id"])
        for row in prediction_rows
        if any(
            isinstance(row.get(marker), Mapping)
            and row[marker].get("changed") is True
            for marker in ("tool_alias_rewrite", "capability_policy")
        )
    }
    base_rows = _latest_rows(base_result_path)
    replacement_rows = _latest_rows(replacement_result_path)
    expected_ids = set(prediction_ids)
    if set(base_rows) != expected_ids:
        raise ValueError("Base result IDs must exactly match prediction IDs")
    if set(replacement_rows) != changed_ids:
        missing = sorted(changed_ids - set(replacement_rows))
        unknown = sorted(set(replacement_rows) - changed_ids)
        raise ValueError(
            "Replacement IDs must exactly match changed prediction IDs: "
            f"missing={missing[:5]} unknown={unknown[:5]}"
        )
    invalid = sorted(
        row_id
        for row_id, row in replacement_rows.items()
        if row.get("status") != "succeeded"
        or not isinstance(row.get("result"), Mapping)
        or row["result"].get("execution_mode") != "expert_runtime"
        or bool(row["result"].get("is_mock", False))
    )
    if invalid:
        raise ValueError(f"Replacement rows are not successful real executions: {invalid[:5]}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row_id in prediction_ids:
            row = replacement_rows.get(row_id, base_rows[row_id])
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "schema_version": "agent.expert_replacement_merge.v1",
        "prediction_count": len(prediction_ids),
        "base_count": len(base_rows),
        "replacement_count": len(replacement_rows),
        "replaced_ids": sorted(replacement_rows),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge a changed-tool expert replacement run.")
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--base-results", required=True, type=Path)
    parser.add_argument("--replacement-results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--merge-manifest", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = merge_expert_replacement_results(
        args.predictions,
        args.base_results,
        args.replacement_results,
        args.output,
    )
    report = summarize_execution(
        prediction_path=args.predictions,
        output_path=args.output,
        run_stats={"expert_replacement_merge": manifest},
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.merge_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.merge_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "CMGE_EXPERT_REPLACEMENT_MERGE_OK "
        f"completed={report['completed_count']}/{report['input_count']} "
        f"replaced={manifest['replacement_count']}"
    )
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
