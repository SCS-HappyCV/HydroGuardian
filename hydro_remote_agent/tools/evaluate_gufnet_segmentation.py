from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hydro_remote_agent.evaluation.segmentation import (  # noqa: E402
    confusion_matrix_1based,
    read_jsonl,
    summarize_segmentation_rows,
)
from hydro_remote_agent.runtime import load_expert_runtime  # noqa: E402
from hydro_remote_agent.schemas.tool_spec import load_tool_registry  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a point segmentation expert on a frozen WCS10M split."
    )
    parser.add_argument("--split", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--tool", default="point_semantic_segmentation")
    parser.add_argument(
        "--registry", default=PROJECT_ROOT / "hydro_remote_agent/configs/tool_registry.yaml"
    )
    parser.add_argument(
        "--runtime", default=PROJECT_ROOT / "hydro_remote_agent/configs/expert_runtime.yaml"
    )
    return parser


def _point_path(row: dict[str, Any], data_root: Path | None) -> Path:
    if data_root is None:
        return Path(row["point_cloud_path"])
    return data_root / str(row["folder_id"]) / "velodyne" / f"{row['patch_id']}.txt"


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def main() -> int:
    args = build_parser().parse_args()
    split_rows = read_jsonl(args.split)
    if args.start < 0:
        raise ValueError("--start must be non-negative")
    split_rows = split_rows[args.start :]
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be positive")
        split_rows = split_rows[: args.limit]
    existing_rows = read_jsonl(args.output)
    completed_ids = {
        str(row["sample_id"]) for row in existing_rows if row.get("status") == "succeeded"
    }

    registry = load_tool_registry(args.registry)
    runtime = load_expert_runtime(args.runtime, registry, work_dir=args.output.parent / "artifacts")
    adapter = runtime.get_adapter(args.tool)
    engine = getattr(adapter, "engine", None)
    if engine is None:
        raise ValueError(f"Tool {args.tool!r} is not backed by an inference engine")
    try:
        runtime.prepare(args.tool)
        for index, split_row in enumerate(split_rows, 1):
            sample_id = str(split_row["sample_id"])
            if sample_id in completed_ids:
                continue
            point_path = _point_path(split_row, args.data_root)
            started = time.perf_counter()
            try:
                prediction = engine.predict(point_path)
                ground_truth = np.loadtxt(point_path, usecols=(-1,), dtype=np.int32, ndmin=1)
                confusion = confusion_matrix_1based(ground_truth, prediction.point_labels)
                result = {
                    "schema_version": "vague_hydro.segmentation_tile.v1",
                    "sample_id": sample_id,
                    "status": "succeeded",
                    "point_cloud_path": str(point_path),
                    "num_points": int(len(ground_truth)),
                    "latency_ms": (time.perf_counter() - started) * 1000.0,
                    "confusion_matrix": confusion.tolist(),
                }
            except Exception as exc:  # keep the formal run resumable across bad tiles
                result = {
                    "schema_version": "vague_hydro.segmentation_tile.v1",
                    "sample_id": sample_id,
                    "status": "failed",
                    "point_cloud_path": str(point_path),
                    "latency_ms": (time.perf_counter() - started) * 1000.0,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(limit=5),
                }
            _append(args.output, result)
            print(
                f"SEGMENTATION_EVAL_PROGRESS {index}/{len(split_rows)} "
                f"sample={sample_id} status={result['status']}",
                flush=True,
            )
    finally:
        runtime.shutdown()

    all_rows = read_jsonl(args.output)
    latest_by_id = {str(row["sample_id"]): row for row in all_rows}
    selected = [latest_by_id[str(row["sample_id"])] for row in split_rows if str(row["sample_id"]) in latest_by_id]
    report = summarize_segmentation_rows(selected, expected_count=len(split_rows))
    report.update(
        tool=args.tool,
        backend=adapter.backend,
        split=str(args.split.resolve()),
        data_root=None if args.data_root is None else str(args.data_root.resolve()),
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"SEGMENTATION_EVAL_DONE status={report['status']} "
        f"succeeded={report['succeeded_count']}/{report['expected_count']} report={args.report}"
    )
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
