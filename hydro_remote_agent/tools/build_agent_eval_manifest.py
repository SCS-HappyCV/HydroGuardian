from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.evaluation.manifest import build_eval_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze and audit Agent Eval v1.")
    parser.add_argument("--config", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    report = build_eval_manifest(
        input_path=Path(config["input"]),
        training_path=Path(config["training"]),
        output_path=Path(config["manifest"]),
        report_path=Path(config["report"]),
        count=int(config.get("count", 240)),
        seed=int(config.get("seed", 20260731)),
    )
    print(
        "AGENT_EVAL_MANIFEST_OK "
        f"count={report['count']} unique_samples={report['unique_sample_id_count']} "
        f"sha256={report['manifest_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
