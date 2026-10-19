from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hydro_remote_agent.evaluation.segmentation import read_jsonl  # noqa: E402
from hydro_remote_agent.runtime import load_expert_runtime  # noqa: E402
from hydro_remote_agent.schemas.tool_spec import load_tool_registry  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare Pointcept Adapter artifacts with the original replay exporter."
    )
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--split", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--reference-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument(
        "--registry", default=PROJECT_ROOT / "hydro_remote_agent/configs/tool_registry.yaml"
    )
    parser.add_argument("--probability-atol", type=float, default=5e-4)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = read_jsonl(args.split)[: args.limit]
    registry = load_tool_registry(args.registry)
    runtime = load_expert_runtime(args.runtime, registry, work_dir=args.output.parent / "artifacts")
    comparisons = []
    try:
        runtime.prepare("point_semantic_segmentation")
        for index, row in enumerate(rows):
            sample_id = str(row["sample_id"])
            point_path = (
                args.data_root
                / str(row["folder_id"])
                / "velodyne"
                / f"{row['patch_id']}.txt"
            )
            result = runtime.invoke(
                "point_semantic_segmentation",
                {"point_cloud_path": str(point_path)},
                invocation_id=f"consistency_{index:03d}_{sample_id}",
            )
            with np.load(result.artifacts["point_labels"]) as payload:
                adapter_labels = payload["point_labels"].astype(np.int64)
            with np.load(result.artifacts["class_probabilities"]) as payload:
                adapter_probabilities = payload["class_probabilities"].astype(np.float32)
            with np.load(args.reference_root / "samples" / f"{sample_id}.npz") as payload:
                reference_labels = payload["prediction"].astype(np.int64) + 1
                reference_probabilities = payload["probabilities"].astype(np.float32)

            label_mismatches = int(np.count_nonzero(adapter_labels != reference_labels))
            max_probability_error = float(
                np.max(np.abs(adapter_probabilities - reference_probabilities))
            )
            passed = label_mismatches == 0 and max_probability_error <= args.probability_atol
            comparisons.append(
                {
                    "sample_id": sample_id,
                    "num_points": int(len(adapter_labels)),
                    "label_mismatches": label_mismatches,
                    "max_probability_error": max_probability_error,
                    "passed": passed,
                }
            )
            print(
                f"POINTCEPT_CONSISTENCY sample={sample_id} passed={passed} "
                f"label_mismatches={label_mismatches} max_probability_error={max_probability_error:.8f}",
                flush=True,
            )
    finally:
        runtime.shutdown()

    report = {
        "schema_version": "hydro_remote_agent.pointcept_consistency.v1",
        "status": "passed" if comparisons and all(row["passed"] for row in comparisons) else "failed",
        "probability_atol": args.probability_atol,
        "comparisons": comparisons,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
