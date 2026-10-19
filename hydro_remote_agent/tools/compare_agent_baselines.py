from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.evaluation.baseline_comparison import METRICS, compare_baselines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the frozen Agent multi-baseline report.")
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--condition", nargs=3, action="append", metavar=("ID", "PREDICTIONS", "REPORT"), required=True)
    parser.add_argument("--reference", default="vaguehydro_lora")
    parser.add_argument("--output", required=True)
    parser.add_argument("--markdown", required=True)
    return parser


def _fmt(value: object) -> str:
    return "-" if value is None else f"{100 * float(value):.2f}%"


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    conditions = {item[0]: (Path(item[1]), Path(item[2])) for item in args.condition}
    report = compare_baselines(Path(args.protocol), conditions, reference_id=args.reference)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    headers = ["Condition", *METRICS]
    lines = ["# Agent Multi-Baseline Comparison", "", "| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] + ["---:"] * len(METRICS)) + "|"]
    for condition_id, payload in report["conditions"].items():
        lines.append("| " + " | ".join([condition_id] + [_fmt(payload["metrics"][name]) for name in METRICS]) + " |")
    lines.extend(["", f"Status: `{report['status']}`", "", "Latency values in the JSON report are batch-amortized estimates; formal wall-clock comparison is run separately."])
    Path(args.markdown).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"AGENT_BASELINE_COMPARISON_OK status={report['status']} conditions={len(conditions)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
