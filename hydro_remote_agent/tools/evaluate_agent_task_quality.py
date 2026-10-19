from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Optional, Sequence

from hydro_remote_agent.evaluation.task_aware_e2e import evaluate_task_aware_conditions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score task-aware quality for frozen Agent executions.")
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--condition", nargs=2, action="append", metavar=("NAME", "RUN"), required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260809)
    parser.add_argument("--reference")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.bootstrap_samples <= 0:
        raise ValueError("--bootstrap-samples must be positive")
    conditions: Dict[str, Path] = {}
    for name, path in args.condition:
        if name in conditions:
            raise ValueError(f"Duplicate condition {name!r}")
        conditions[name] = Path(path)
    report = evaluate_task_aware_conditions(
        gold_path=args.gold,
        condition_paths=conditions,
        annotation_path=args.annotations,
        data_root=args.data_root,
        output_dir=args.output_dir,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
        reference_condition=args.reference,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"AGENT_TASK_QUALITY_OK conditions={len(conditions)} gold={report['gold_count']} "
        f"report={args.report}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
