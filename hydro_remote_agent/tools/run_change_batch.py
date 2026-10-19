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


def gpu(gpu_id: int) -> dict[str, int] | None:
    try:
        row = subprocess.check_output(["nvidia-smi", f"--id={gpu_id}", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"], text=True, timeout=10).strip()
        mem, util = [int(x.strip()) for x in row.split(",")]
        return {"memory_used_mib": mem, "utilization_percent": util}
    except Exception:
        return None


def invoke(base: str, tool: str, invocation: str, args: dict[str, Any], timeout: float, gpu_id: int) -> dict[str, Any]:
    req = urllib.request.Request(f"{base.rstrip('/')}/internal/tools/{tool}/invoke", data=json.dumps({"invocation_id": invocation, "arguments": args, "timeout_seconds": timeout}).encode(), headers={"Content-Type": "application/json"}, method="POST")
    before, started = gpu(gpu_id), time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout + 30) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
    return {"tool": tool, "invocation_id": invocation, "wall_time_seconds": time.perf_counter() - started, "gpu_before": before, "gpu_after": gpu(gpu_id), "result": result, "is_mock": result.get("is_mock"), "backend": result.get("backend"), "status": result.get("status")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:28080")
    parser.add_argument("--pair", action="append", nargs=3, metavar=("PAIR_ID", "BEFORE", "AFTER"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--gpu-id", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=1200)
    args = parser.parse_args()
    report: dict[str, Any] = {"schema_version": "vaguehydro.real_change_batch.v1", "run_id": args.run_id, "started_at": datetime.now(timezone.utc).isoformat(), "pairs": [], "status": "running"}
    for index, (pair_id, before, after) in enumerate(args.pair, start=1):
        change = invoke(args.base_url, "image_change_detection", f"{args.run_id}-{pair_id}-change", {"before_image_path": before, "after_image_path": after, "change_threshold": 0.0005, "minimum_region_pixels": 0, "return_probability_map": True}, args.timeout_seconds, args.gpu_id)
        result = change["result"]
        verify = invoke(args.base_url, "result_quality_verification", f"{args.run_id}-{pair_id}-verify", {"result_path": result["manifest_path"], "source_tool": "image_change_detection", "result_artifacts": result["artifacts"], "image_path": after, "minimum_confidence": 0.6, "maximum_empty_ratio": 0.999}, args.timeout_seconds, args.gpu_id)
        metrics = result.get("metrics", {})
        verify_metrics = verify.get("result", {}).get("metrics", {})
        verdict = verify_metrics.get("verdict")
        status = "passed" if change.get("is_mock") is False and verdict == "passed" else ("passed_with_warning" if change.get("is_mock") is False and verdict == "warning" else "failed")
        pair = {"pair_id": pair_id, "before": before, "after": after, "change": change, "verification": verify, "status": status, "changed_ratio": metrics.get("changed_ratio"), "region_count": metrics.get("region_count")}
        report["pairs"].append(pair)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        (args.output.parent / f"{args.output.stem}.progress.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    statuses = {pair["status"] for pair in report["pairs"]}
    report["status"] = "failed" if "failed" in statuses else ("passed_with_warning" if "passed_with_warning" in statuses else "passed")
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "pairs": len(report["pairs"]), "passed": sum(pair["status"] == "passed" for pair in report["pairs"])}, ensure_ascii=False), flush=True)
    return 0 if report["status"] in {"passed", "passed_with_warning"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
