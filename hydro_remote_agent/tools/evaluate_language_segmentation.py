from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hydro_remote_agent.evaluation.language_segmentation import (  # noqa: E402
    binary_mask_metrics,
    summarize_language_segmentation_rows,
)
from hydro_remote_agent.evaluation.segmentation import read_jsonl  # noqa: E402
from hydro_remote_agent.runtime import load_expert_runtime  # noqa: E402
from hydro_remote_agent.schemas.tool_spec import load_tool_registry  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate HydroProgram3D language masks on frozen WCS10M tasks.")
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--split", required=True, type=Path, help="Frozen test.txt containing sample IDs.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--task-types",
        nargs="+",
        choices=("class", "attribute", "relation", "no_target"),
        help="Evaluate only the selected task types.",
    )
    parser.add_argument(
        "--max-per-task-type",
        type=int,
        help="Keep at most this many tasks from each selected task type.",
    )
    parser.add_argument(
        "--mask-thresholds",
        nargs="+",
        type=float,
        help="Also score probability masks at these thresholds for validation calibration.",
    )
    parser.add_argument("--registry", default=PROJECT_ROOT / "hydro_remote_agent/configs/tool_registry.yaml")
    parser.add_argument("--runtime", default=PROJECT_ROOT / "hydro_remote_agent/configs/expert_runtime.yaml")
    return parser


def _iter_tasks(annotation_path: Path, sample_ids: set[str]) -> Iterable[dict[str, Any]]:
    for record in read_jsonl(annotation_path):
        sample_id = str(record.get("sample_id", ""))
        if sample_id not in sample_ids:
            continue
        for item in record.get("texts", []):
            yield {"record": record, "text": item}


def _resolve_assets(record: dict[str, Any], data_root: Path | None) -> tuple[Path, Path]:
    if data_root is None:
        return Path(record["ortho_image_path"]), Path(record["point_cloud_path"])
    region_id = str(record["region_id"])
    patch_id = str(record["patch_id"])
    return (
        data_root / region_id / "image" / f"{patch_id}.png",
        data_root / region_id / "velodyne" / f"{patch_id}.txt",
    )


def _target_mask(points: Any, text_item: dict[str, Any]) -> np.ndarray:
    from wcs_unified.dataset import build_rule_target_mask

    xyz = points[:, :3]
    labels = points[:, 6].long()
    rule = text_item.get("target_mask_rule")
    if rule:
        return build_rule_target_mask(xyz, labels, rule).numpy()
    target = np.zeros(len(points), dtype=np.bool_)
    if not bool(text_item.get("is_no_target", False)):
        for label_id in text_item.get("target_label_ids", []):
            target |= labels.numpy() == int(label_id)
    return target


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def main() -> int:
    args = build_parser().parse_args()
    from wcs_unified.dataset import load_point_tensor

    sample_ids = {line.strip() for line in args.split.read_text(encoding="utf-8").splitlines() if line.strip()}
    tasks = list(_iter_tasks(args.annotations, sample_ids))
    if args.task_types:
        selected_task_types = set(args.task_types)
        tasks = [task for task in tasks if task["text"].get("task_type") in selected_task_types]
    if args.max_per_task_type is not None:
        if args.max_per_task_type < 1:
            raise ValueError("--max-per-task-type must be positive")
        task_counts: dict[str, int] = defaultdict(int)
        limited_tasks = []
        for task in tasks:
            task_type = str(task["text"].get("task_type", "unknown"))
            if task_counts[task_type] >= args.max_per_task_type:
                continue
            task_counts[task_type] += 1
            limited_tasks.append(task)
        tasks = limited_tasks
    mask_thresholds = []
    for threshold in args.mask_thresholds or []:
        if not 0.0 < threshold < 1.0:
            raise ValueError("--mask-thresholds values must be between 0 and 1")
        if threshold not in mask_thresholds:
            mask_thresholds.append(threshold)
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be positive")
        tasks = tasks[: args.limit]
    completed = {str(row.get("request_id")) for row in read_jsonl(args.output) if row.get("status") == "succeeded"}
    registry = load_tool_registry(args.registry)
    runtime = load_expert_runtime(args.runtime, registry, work_dir=args.output.parent / "artifacts")
    try:
        runtime.prepare("language_guided_point_segmentation")
        for index, task in enumerate(tasks, 1):
            record, text_item = task["record"], task["text"]
            request_id = str(text_item["text_id"])
            if request_id in completed:
                continue
            image_path, point_path = _resolve_assets(record, args.data_root)
            started = time.perf_counter()
            try:
                points = load_point_tensor(str(point_path))
                target = _target_mask(points, text_item)
                result = runtime.invoke(
                    "language_guided_point_segmentation",
                    {"image_path": str(image_path), "point_cloud_path": str(point_path), "query": str(text_item["text"])},
                    invocation_id=f"eval_{index:05d}",
                )
                with np.load(result.artifacts["target_mask"], allow_pickle=False) as payload:
                    prediction = np.asarray(payload["target_mask"])
                threshold_metrics = None
                if mask_thresholds:
                    with np.load(result.artifacts["target_probabilities"], allow_pickle=False) as payload:
                        probabilities = np.asarray(payload["target_probabilities"])
                    threshold_metrics = {
                        f"{threshold:g}": binary_mask_metrics(target, probabilities >= threshold)
                        for threshold in mask_thresholds
                    }
                row = {
                    "request_id": request_id,
                    "sample_id": record["sample_id"],
                    "task_type": text_item.get("task_type", "unknown"),
                    "is_no_target": bool(text_item.get("is_no_target", False)),
                    "predicted_no_target": bool(result.metrics.get("no_target", False)),
                    "abstained": bool(result.metrics.get("abstained", False)),
                    "diagnostics": {
                        key: result.metrics.get(key)
                        for key in (
                            "execution_confidence",
                            "abstain_probability",
                            "selected_candidate_index",
                            "candidate_posterior_scores",
                            "posterior_no_target_mass",
                            "probability_mean",
                            "probability_p99",
                            "probability_max",
                            "inferred_task_type",
                            "applied_mask_threshold",
                            "model_no_target",
                            "calibrated_no_target",
                        )
                    },
                    "status": "succeeded",
                    "latency_ms": (time.perf_counter() - started) * 1000.0,
                    "metrics": binary_mask_metrics(target, prediction),
                    "manifest_path": result.manifest_path,
                }
                if threshold_metrics is not None:
                    row["threshold_metrics"] = threshold_metrics
            except Exception as exc:
                row = {
                    "request_id": request_id,
                    "sample_id": record["sample_id"],
                    "task_type": text_item.get("task_type", "unknown"),
                    "is_no_target": bool(text_item.get("is_no_target", False)),
                    "status": "failed",
                    "latency_ms": (time.perf_counter() - started) * 1000.0,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(limit=5),
                }
            _append(args.output, row)
            print(f"LANGUAGE_EVAL_PROGRESS {index}/{len(tasks)} request={request_id} status={row['status']}", flush=True)
    finally:
        runtime.shutdown()

    latest = {str(row["request_id"]): row for row in read_jsonl(args.output)}
    selected = [latest[str(task["text"]["text_id"])] for task in tasks if str(task["text"]["text_id"]) in latest]
    report = summarize_language_segmentation_rows(selected, expected_count=len(tasks))
    report.update(annotations=str(args.annotations.resolve()), split=str(args.split.resolve()))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"LANGUAGE_EVAL_DONE status={report['status']} completed={report['completed_count']}/{report['expected_count']}")
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
