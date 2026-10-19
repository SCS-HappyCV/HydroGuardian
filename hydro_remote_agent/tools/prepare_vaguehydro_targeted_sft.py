from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def rank(record: dict[str, Any], seed: int) -> str:
    return hashlib.sha256(f"{seed}:{record.get('id', '')}".encode()).hexdigest()


def action_type(record: dict[str, Any]) -> str:
    target = json.loads(record["messages"][-1]["content"])
    return str(target.get("action", {}).get("type", ""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--workflow-limit", type=int, default=256)
    parser.add_argument("--tool-call-limit", type=int, default=128)
    parser.add_argument("--direct-answer-limit", type=int, default=64)
    args = parser.parse_args()
    buckets: dict[str, list[dict[str, Any]]] = {"workflow": [], "tool_call": [], "direct_answer": []}
    with Path(args.input).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                kind = action_type(record)
                if kind in buckets:
                    buckets[kind].append(record)
    limits = {
        "workflow": args.workflow_limit,
        "tool_call": args.tool_call_limit,
        "direct_answer": args.direct_answer_limit,
    }
    selected: list[dict[str, Any]] = []
    for kind, values in buckets.items():
        values.sort(key=lambda record: rank(record, args.seed))
        selected.extend(values[: limits[kind]])
    selected.sort(key=lambda record: str(record.get("id", "")))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in selected:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    report = {
        "schema_version": "vaguehydro.targeted_sft.v2",
        "seed": args.seed,
        "source": str(args.input),
        "output": str(args.output),
        "counts_available": {key: len(value) for key, value in buckets.items()},
        "counts_selected": {key: sum(action_type(record) == key for record in selected) for key in buckets},
        "record_count": len(selected),
        "purpose": "increase explicit tool-call and workflow supervision for invalid tool arguments and exact tool sequences",
        "formal_training": False,
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
