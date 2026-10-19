from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.evaluation.system_ablation import ABLATION_MODES, run_system_ablation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Derive controlled system ablations from a completed Agent execution run."
    )
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--baseline-results", required=True)
    parser.add_argument("--mode", choices=ABLATION_MODES, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_system_ablation(
        prediction_path=Path(args.predictions),
        baseline_results_path=Path(args.baseline_results),
        output_path=Path(args.output),
        report_path=Path(args.report),
        mode=args.mode,
    )
    metrics = report["metrics"]
    print(
        "VAGUE_HYDRO_SYSTEM_ABLATION_OK "
        f"mode={args.mode} success={metrics['task_success_count']}/"
        f"{metrics['request_count']} affected={report['ablation']['affected_request_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
