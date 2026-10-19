from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json, read_jsonl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Split pending routing records into disjoint shards.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--completed", required=True)
    parser.add_argument("--output-prefix", required=True)
    parser.add_argument("--shards", type=int, required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.shards <= 0:
        raise ValueError("shards must be positive")
    records = read_jsonl(Path(args.input))
    completed = {str(row["id"]) for row in read_jsonl(Path(args.completed))}
    pending = [record for record in records if str(record["id"]) not in completed]
    shard_rows = [[] for _ in range(args.shards)]
    for index, record in enumerate(pending):
        shard_rows[index % args.shards].append(record)
    prefix = Path(args.output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for index, rows in enumerate(shard_rows):
        path = prefix.parent / f"{prefix.name}_{index}.jsonl"
        path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")
        print(f"SHARD_OK index={index} records={len(rows)} output={path}")
    print(f"ROUTING_SHARD_OK completed={len(completed)} pending={len(pending)} shards={args.shards}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
