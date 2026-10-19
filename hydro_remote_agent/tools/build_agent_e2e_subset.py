from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json, read_jsonl
from hydro_remote_agent.evaluation.e2e_comparison import freeze_stratified_subset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze the balanced 50-request E2E comparison set.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--seed", type=int, default=20260808)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    selected, report = freeze_stratified_subset(read_jsonl(Path(args.input)), seed=args.seed)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(canonical_json(row) + "\n" for row in selected), encoding="utf-8")
    report["source_path"] = str(Path(args.input))
    report["output_path"] = str(output)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"AGENT_E2E_SUBSET_OK records={len(selected)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
