from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json, read_jsonl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge disjoint routing predictions in manifest order.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output", required=True)
    return parser


def merge_predictions(manifest: Path, inputs: Sequence[Path], output: Path) -> int:
    manifest_rows = read_jsonl(manifest)
    expected_ids = [str(row["id"]) for row in manifest_rows]
    predictions: Dict[str, Dict[str, Any]] = {}
    for path in inputs:
        for row in read_jsonl(path):
            record_id = str(row.get("id", ""))
            if not record_id:
                raise ValueError(f"{path} contains a prediction without id")
            if record_id in predictions:
                raise ValueError(f"duplicate prediction id {record_id!r}")
            predictions[record_id] = row
    missing = [record_id for record_id in expected_ids if record_id not in predictions]
    extra = sorted(set(predictions) - set(expected_ids))
    if missing or extra:
        raise ValueError(f"prediction population mismatch: missing={len(missing)} extra={len(extra)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(canonical_json(predictions[record_id]) + "\n" for record_id in expected_ids),
        encoding="utf-8",
    )
    return len(expected_ids)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    count = merge_predictions(
        Path(args.manifest), [Path(value) for value in args.input], Path(args.output)
    )
    print(f"ROUTING_MERGE_OK records={count} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
