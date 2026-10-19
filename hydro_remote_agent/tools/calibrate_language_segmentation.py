from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hydro_remote_agent.evaluation.language_calibration import (  # noqa: E402
    calibrate_no_target,
    select_mask_thresholds,
)
from hydro_remote_agent.evaluation.segmentation import read_jsonl  # noqa: E402
from hydro_remote_agent.runtime.hydro_program3d_engine import infer_program_task_type  # noqa: E402


def _attach_runtime_task_type(row: dict) -> dict:
    row = dict(row)
    diagnostics = dict(row.get("diagnostics") or {})
    runtime_type = diagnostics.get("inferred_task_type")
    if runtime_type not in {"class", "attribute", "relation"}:
        manifest_path = row.get("manifest_path")
        if manifest_path and Path(manifest_path).is_file():
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            runtime_type = (manifest.get("metrics") or {}).get("inferred_task_type")
            if runtime_type not in {"class", "attribute", "relation"}:
                program_path = (manifest.get("artifacts") or {}).get("compiled_program")
                if program_path and Path(program_path).is_file():
                    payload = json.loads(Path(program_path).read_text(encoding="utf-8"))
                    runtime_type = infer_program_task_type(dict(payload.get("selected_program") or {}))
    if runtime_type in {"class", "attribute", "relation"}:
        row["runtime_task_type"] = runtime_type
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate language segmentation using validation rows only.")
    parser.add_argument("--results", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for path in args.results:
        rows.extend(_attach_runtime_task_type(row) for row in read_jsonl(path))
    report = {
        "schema_version": "vague_hydro.language_calibration.v1",
        "source_results": [str(path.resolve()) for path in args.results],
        "request_count": len(rows),
        "mask_thresholds": select_mask_thresholds(rows),
        "no_target": calibrate_no_target(rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
