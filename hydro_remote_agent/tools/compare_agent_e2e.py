from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Optional, Sequence

from hydro_remote_agent.evaluation.e2e_comparison import compare_e2e_conditions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare frozen end-to-end Agent conditions.")
    parser.add_argument("--gold", required=True)
    parser.add_argument("--condition", nargs=2, action="append", metavar=("NAME", "RUN"), required=True)
    parser.add_argument("--reference")
    parser.add_argument("--output", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    conditions: Dict[str, Path] = {}
    for name, path in args.condition:
        if name in conditions:
            raise ValueError(f"duplicate condition {name!r}")
        conditions[name] = Path(path)
    report = compare_e2e_conditions(
        Path(args.gold),
        conditions,
        reference_condition=args.reference,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"AGENT_E2E_COMPARISON_OK conditions={len(conditions)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
