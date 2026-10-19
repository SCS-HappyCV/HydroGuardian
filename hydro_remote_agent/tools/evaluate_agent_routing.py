from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.evaluation.routing import evaluate_routing
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate VagueHydro Agent routing.")
    parser.add_argument(
        "--gold",
        action="append",
        required=True,
        help="Gold generated or SFT JSONL; may be repeated.",
    )
    parser.add_argument("--predictions", required=True)
    parser.add_argument(
        "--registry",
        default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml"),
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-error-examples", type=int, default=20)
    parser.add_argument("--bootstrap-samples", type=int, default=0)
    parser.add_argument("--bootstrap-seed", type=int, default=20260731)
    parser.add_argument("--bootstrap-confidence", type=float, default=0.95)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = evaluate_routing(
        gold_paths=[Path(path) for path in args.gold],
        prediction_path=Path(args.predictions),
        registry=load_tool_registry(args.registry),
        max_error_examples=max(args.max_error_examples, 0),
        bootstrap_samples=max(args.bootstrap_samples, 0),
        bootstrap_seed=args.bootstrap_seed,
        bootstrap_confidence=args.bootstrap_confidence,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    metrics = report["metrics"]
    print(
        "VAGUE_HYDRO_ROUTING_EVAL_OK "
        f"gold={report['gold_count']} predictions={report['prediction_count']} "
        f"schema_valid={metrics['schema_valid_rate']:.6f} "
        f"action={metrics['action_type_accuracy']:.6f} "
        f"tool={metrics['tool_selection_accuracy']} output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
