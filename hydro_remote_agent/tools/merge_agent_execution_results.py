from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hydro_remote_agent.evaluation.execution import (  # noqa: E402
    merge_execution_results,
    summarize_execution,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge real reruns into a frozen Agent execution result set.")
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--base-results", required=True, type=Path)
    parser.add_argument("--replacement-results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--merge-manifest", required=True, type=Path)
    args = parser.parse_args()

    manifest = merge_execution_results(
        prediction_path=args.predictions,
        base_result_path=args.base_results,
        replacement_result_path=args.replacement_results,
        output_path=args.output,
    )
    report = summarize_execution(
        prediction_path=args.predictions,
        output_path=args.output,
        run_stats={"merge": manifest},
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.merge_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.merge_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "VAGUE_HYDRO_EXECUTION_MERGE_OK "
        f"completed={report['completed_count']}/{report['input_count']} "
        f"replaced={manifest['replacement_count']} mock_skipped={report['mock_skipped_count']}"
    )
    return 0 if report["status"] == "completed" and report["mock_skipped_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
