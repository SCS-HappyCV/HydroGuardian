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


def post(base_url: str, tool: str, invocation_id: str, arguments: dict[str, Any], timeout: float, gpu_id: int) -> dict[str, Any]:
    payload = {"invocation_id": invocation_id, "arguments": arguments, "timeout_seconds": timeout}
    request = urllib.request.Request(f"{base_url.rstrip('/')}/internal/tools/{tool}/invoke", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    before = gpu_sample(gpu_id)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout + 30) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
    return {"tool": tool, "invocation_id": invocation_id, "wall_time_seconds": time.perf_counter() - started, "gpu_before": before, "gpu_after": gpu_sample(gpu_id), "result": result, "is_mock": result.get("is_mock"), "backend": result.get("backend"), "status": result.get("status")}


def gpu_sample(gpu_id: int) -> dict[str, int] | None:
    try:
        out = subprocess.check_output(["nvidia-smi", f"--id={gpu_id}", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"], text=True, timeout=10).strip()
        memory, utilization = (int(x.strip()) for x in out.split(","))
        return {"memory_used_mib": memory, "utilization_percent": utilization}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:28080")
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", default="runs/hydro_remote_agent/vaguehydro_legality_repair_pilot_v3")
    parser.add_argument("--gpu-id", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=1200)
    args = parser.parse_args()
    output = Path(args.output_dir) / f"REAL_CHANGE_CANARY_{args.run_id}.json"
    change = post(args.base_url, "image_change_detection", f"{args.run_id}-change", {"before_image_path": args.before, "after_image_path": args.after, "change_threshold": 0.0005, "minimum_region_pixels": 0, "return_probability_map": True}, args.timeout_seconds, args.gpu_id)
    result = change["result"]
    verify = post(args.base_url, "result_quality_verification", f"{args.run_id}-verify", {"result_path": result["manifest_path"], "source_tool": "image_change_detection", "result_artifacts": result["artifacts"], "image_path": args.after, "minimum_confidence": 0.6, "maximum_empty_ratio": 0.999}, args.timeout_seconds, args.gpu_id)
    verify_result = verify.get("result", {})
    verdict = verify_result.get("metrics", {}).get("verdict")
    verify_passed = verify_result.get("passed") is True or verdict == "passed"
    status = "passed" if change.get("is_mock") is False and verify_passed else ("passed_with_warning" if change.get("is_mock") is False and verdict == "warning" else "failed")
    report = {"schema_version": "vaguehydro.real_change_canary.v1", "run_id": args.run_id, "started_at": datetime.now(timezone.utc).isoformat(), "inputs": {"before_image_path": args.before, "after_image_path": args.after, "registered_pair": True}, "steps": [change, verify], "status": status, "finished_at": datetime.now(timezone.utc).isoformat()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "change_backend": change.get("backend"), "verify_backend": verify.get("backend"), "change_is_mock": change.get("is_mock"), "verify_passed": verify_passed}, ensure_ascii=False), flush=True)
    return 0 if report["status"] in {"passed", "passed_with_warning"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
