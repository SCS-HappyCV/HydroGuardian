from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json, read_jsonl
from hydro_remote_agent.baselines.rule_router import RuleRouter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the deterministic Rule Router baseline.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = Path(args.output)
    records = read_jsonl(Path(args.input))
    completed = set()
    if args.resume and output_path.exists():
        completed = {str(row["id"]) for row in read_jsonl(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.resume and output_path.exists() else "w"
    router = RuleRouter()
    with output_path.open(mode, encoding="utf-8", newline="\n") as handle:
        for record in records:
            record_id = str(record["id"])
            if record_id in completed:
                continue
            result = router.plan(record)
            handle.write(canonical_json({
                "id": record_id,
                "prediction": result.request,
                "inference": {"baseline": "rule_router", **result.trace},
            }) + "\n")
    print(f"RULE_ROUTING_PREDICT_OK records={len(records)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
