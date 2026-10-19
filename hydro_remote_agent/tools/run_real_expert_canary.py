from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SAMPLES = (
    ("00_000004", "grassland", 9),
    ("00_000006", "grassland", 9),
    ("00_000014", "waterline", 13),
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout + 30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Control plane returned a non-object")
    return result


def gpu_sample(gpu_id: int) -> dict[str, int] | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", f"--id={gpu_id}", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
            text=True,
            timeout=10,
        ).strip()
        memory, utilization = (int(x.strip()) for x in out.split(","))
        return {"memory_used_mib": memory, "utilization_percent": utilization}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def invoke(base_url: str, tool: str, invocation_id: str, arguments: dict[str, Any], timeout: float, gpu_id: int) -> dict[str, Any]:
    before = gpu_sample(gpu_id)
    started = time.perf_counter()
    result = post_json(
        f"{base_url.rstrip('/')}/internal/tools/{tool}/invoke",
        {"invocation_id": invocation_id, "arguments": arguments, "timeout_seconds": timeout},
        timeout,
    )
    after = gpu_sample(gpu_id)
    return {
        "tool": tool,
        "invocation_id": invocation_id,
        "wall_time_seconds": time.perf_counter() - started,
        "gpu_before": before,
        "gpu_after": after,
        "result": result,
        "is_mock": result.get("is_mock"),
        "backend": result.get("backend"),
        "status": result.get("status"),
    }


def verify(base_url: str, source: dict[str, Any], source_tool: str, sample: dict[str, Any], run_id: str, index: int, timeout: float, gpu_id: int) -> dict[str, Any]:
    result = source["result"]
    arguments = {
        "result_path": result["manifest_path"],
        "source_tool": source_tool,
        "result_artifacts": result["artifacts"],
        "minimum_confidence": 0.6,
        "maximum_empty_ratio": 0.999,
    }
    if source_tool == "language_guided_point_segmentation":
        arguments.update({"image_path": sample["image_path"], "point_cloud_path": sample["point_cloud_path"]})
    else:
        arguments["point_cloud_path"] = sample["point_cloud_path"]
    return invoke(base_url, "result_quality_verification", f"{run_id}-verify-{index:02d}", arguments, timeout, gpu_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Canary real experts on frozen WCS10M test tiles.")
    parser.add_argument("--base-url", default="http://127.0.0.1:28080")
    parser.add_argument("--project-root", default="/workspace/HydroGuardian")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", default="runs/hydro_remote_agent/real_expert_canary_v1")
    parser.add_argument("--gpu-id", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=1200)
    args = parser.parse_args()

    root = Path(args.project_root)
    split_map = json.loads((root / "data/wcs10m_primary_split_map.json").read_text(encoding="utf-8"))["assignments"]
    manifest = {}
    with (root / "benchmark/10M/tiles_manifest.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            manifest[item["sample_id"]] = item

    report: dict[str, Any] = {
        "schema_version": "vaguehydro.real_expert_canary.v1",
        "run_id": args.run_id,
        "started_at": now(),
        "split_protocol": "wcs10m_primary",
        "split_field": "wcs10m_primary_split",
        "selected_samples": [],
        "steps": [],
        "blocked_capabilities": {
            "image_change_detection": {
                "status": "blocked",
                "reason": "Remote host has no independent registered before/after test pair; local R03_C04 pair is not available to remote worker.",
            }
        },
        "status": "running",
    }
    output = Path(args.output_dir) / args.run_id
    output.mkdir(parents=True, exist_ok=True)

    for sample_id, label_name, class_id in SAMPLES:
        if split_map.get(sample_id) != "test":
            raise RuntimeError(f"Sample {sample_id} is not assigned to frozen test split")
        item = manifest[sample_id]
        region = item["region_id"]
        image = f"{root}/benchmark/10M/{region}/image/{item['patch_id']}.png"
        points = f"{root}/benchmark/10M/{region}/velodyne/{item['patch_id']}.txt"
        if not Path(image).is_file() or not Path(points).is_file():
            raise FileNotFoundError(f"Missing canary input for {sample_id}: {image}, {points}")
        sample = {
            "sample_id": sample_id,
            "split": split_map[sample_id],
            "scene_type": item.get("scene_type"),
            "present_label_ids": item.get("present_label_ids", []),
            "present_label_names": item.get("present_label_names", []),
            "num_points": item.get("num_points"),
            "image_path": image,
            "point_cloud_path": points,
            "query": f"segment the {label_name} points",
            "target_class_id": class_id,
        }
        report["selected_samples"].append(sample)
        point = invoke(
            args.base_url,
            "point_semantic_segmentation",
            f"{args.run_id}-{sample_id}-point",
            {"point_cloud_path": points, "target_class_ids": [class_id], "return_probabilities": True},
            args.timeout_seconds,
            args.gpu_id,
        )
        point["sample_id"] = sample_id
        report["steps"].append(point)
        report["steps"].append(verify(args.base_url, point, "point_semantic_segmentation", sample, args.run_id, len(report["steps"]), args.timeout_seconds, args.gpu_id))

        language = invoke(
            args.base_url,
            "language_guided_point_segmentation",
            f"{args.run_id}-{sample_id}-language",
            {"image_path": image, "point_cloud_path": points, "query": sample["query"], "target_class_ids": [class_id], "return_probabilities": True},
            args.timeout_seconds,
            args.gpu_id,
        )
        language["sample_id"] = sample_id
        report["steps"].append(language)
        report["steps"].append(verify(args.base_url, language, "language_guided_point_segmentation", sample, args.run_id, len(report["steps"]), args.timeout_seconds, args.gpu_id))

        (output / "CANARY_PROGRESS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    report["status"] = "passed"
    report["finished_at"] = now()
    (output / "CANARY_RESULTS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (Path(args.output_dir) / "LATEST_RUN.txt").write_text(str(output.resolve()) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "samples": len(report["selected_samples"]), "steps": len(report["steps"]), "blocked_capabilities": report["blocked_capabilities"]}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
