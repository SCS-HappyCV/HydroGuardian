from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


EXPECTED_BACKENDS = {
    "geometry_relation_analysis": "geometry_numpy",
    "point_semantic_segmentation": "gufnet_3d_inference",
    "image_change_detection": "rfanet_change_detection",
    "language_guided_point_segmentation": "hydro_program3d_inference",
    "result_quality_verification": "deterministic_quality_verification",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_json(url: str, payload: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout + 30.0) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Control plane returned a non-object response")
    return parsed


def _gpu_sample(gpu_id: int) -> dict[str, int] | None:
    command = [
        "nvidia-smi",
        f"--id={gpu_id}",
        "--query-gpu=memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        output = subprocess.check_output(command, text=True, timeout=10).strip()
        memory_used, utilization = [int(value.strip()) for value in output.split(",")]
        return {"memory_used_mib": memory_used, "utilization_percent": utilization}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


class GpuMonitor:
    def __init__(self, gpu_id: int, interval_seconds: float = 1.0) -> None:
        self.gpu_id = gpu_id
        self.interval_seconds = interval_seconds
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "GpuMonitor":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            sample = _gpu_sample(self.gpu_id)
            if sample is not None:
                self.samples.append({"timestamp": _utc_now(), **sample})
            self._stop.wait(self.interval_seconds)

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=15.0)
        sample = _gpu_sample(self.gpu_id)
        if sample is not None:
            self.samples.append({"timestamp": _utc_now(), **sample})

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return {"gpu_id": self.gpu_id, "samples": 0}
        return {
            "gpu_id": self.gpu_id,
            "samples": len(self.samples),
            "memory_start_mib": self.samples[0]["memory_used_mib"],
            "memory_peak_mib": max(item["memory_used_mib"] for item in self.samples),
            "memory_end_mib": self.samples[-1]["memory_used_mib"],
            "utilization_peak_percent": max(item["utilization_percent"] for item in self.samples),
        }


def _validate_result(tool: str, result: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("status") != "succeeded":
        errors.append(f"status={result.get('status')!r}")
    if result.get("tool") != tool:
        errors.append(f"tool={result.get('tool')!r}")
    if result.get("backend") != EXPECTED_BACKENDS[tool]:
        errors.append(f"backend={result.get('backend')!r}")
    if result.get("is_mock") is not False:
        errors.append(f"is_mock={result.get('is_mock')!r}")
    manifest_path = result.get("manifest_path")
    if not isinstance(manifest_path, str) or not manifest_path.startswith("artifact://"):
        errors.append("manifest_path is not a published artifact URI")
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        errors.append("artifacts are missing")
    elif any(not isinstance(value, str) or not value.startswith("artifact://") for value in artifacts.values()):
        errors.append("one or more artifacts were not published")
    return errors


def _write_state(output_dir: Path, report: Mapping[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "SMOKE_RESULTS.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    examples = project_root / "hydro_remote_agent" / "examples"
    paths = {
        "geometry_points": examples / "geometry_smoke_points.xyz",
        "geometry_labels": examples / "geometry_smoke_labels.json",
        "point_cloud": examples / "language_smoke_points.txt",
        "before_image": examples / "change_smoke_before.png",
        "after_image": examples / "change_smoke_after.png",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing smoke inputs: {missing}")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir).resolve() / run_id
    report: dict[str, Any] = {
        "schema_version": "vaguehydro.real_expert_smoke.v1",
        "run_id": run_id,
        "started_at": _utc_now(),
        "base_url": args.base_url,
        "gpu_id": args.gpu_id,
        "input_paths": {name: str(path.resolve()) for name, path in paths.items()},
        "steps": [],
        "status": "running",
    }
    _write_state(output_dir, report)

    calls: list[tuple[str, dict[str, Any]]] = [
        (
            "geometry_relation_analysis",
            {
                "point_cloud_path": str(paths["geometry_points"].resolve()),
                "segmentation_result_path": str(paths["geometry_labels"].resolve()),
                "operation": "class_statistics",
                "target_class_id": 1,
            },
        ),
        (
            "point_semantic_segmentation",
            {
                "point_cloud_path": str(paths["point_cloud"].resolve()),
                "return_probabilities": True,
            },
        ),
        (
            "image_change_detection",
            {
                "before_image_path": str(paths["before_image"].resolve()),
                "after_image_path": str(paths["after_image"].resolve()),
                "change_threshold": 0.0005,
                "minimum_region_pixels": 0,
                "return_probability_map": True,
            },
        ),
        (
            "language_guided_point_segmentation",
            {
                "image_path": str(paths["after_image"].resolve()),
                "point_cloud_path": str(paths["point_cloud"].resolve()),
                "query": "segment the road points",
                "return_probabilities": True,
            },
        ),
    ]

    try:
        language_result: dict[str, Any] | None = None
        for index, (tool, arguments) in enumerate(calls, start=1):
            invocation_id = f"real-smoke-{run_id}-{index:02d}-{tool[:24]}"
            payload = {
                "invocation_id": invocation_id,
                "arguments": arguments,
                "timeout_seconds": args.timeout_seconds,
            }
            started = time.perf_counter()
            with GpuMonitor(args.gpu_id) as monitor:
                result = _request_json(
                    f"{args.base_url.rstrip('/')}/internal/tools/{tool}/invoke",
                    payload,
                    args.timeout_seconds,
                )
            validation_errors = _validate_result(tool, result)
            step = {
                "index": index,
                "tool": tool,
                "invocation_id": invocation_id,
                "status": "passed" if not validation_errors else "failed",
                "wall_time_seconds": time.perf_counter() - started,
                "gpu": monitor.summary(),
                "validation_errors": validation_errors,
                "result": result,
            }
            report["steps"].append(step)
            _write_state(output_dir, report)
            print(json.dumps({key: step[key] for key in ("tool", "status", "wall_time_seconds", "gpu")}), flush=True)
            if validation_errors:
                raise RuntimeError(f"{tool} output contract failed: {validation_errors}")
            if tool == "language_guided_point_segmentation":
                language_result = result

        if language_result is None:
            raise RuntimeError("Language result is unavailable for verification")
        verifier_tool = "result_quality_verification"
        verifier_arguments = {
            "result_path": language_result["manifest_path"],
            "source_tool": "language_guided_point_segmentation",
            "result_artifacts": language_result["artifacts"],
            "image_path": str(paths["after_image"].resolve()),
            "point_cloud_path": str(paths["point_cloud"].resolve()),
            "minimum_confidence": 0.6,
            "maximum_empty_ratio": 0.999,
        }
        verifier_id = f"real-smoke-{run_id}-05-verifier"
        started = time.perf_counter()
        with GpuMonitor(args.gpu_id) as monitor:
            verifier_result = _request_json(
                f"{args.base_url.rstrip('/')}/internal/tools/{verifier_tool}/invoke",
                {
                    "invocation_id": verifier_id,
                    "arguments": verifier_arguments,
                    "timeout_seconds": args.timeout_seconds,
                },
                args.timeout_seconds,
            )
        validation_errors = _validate_result(verifier_tool, verifier_result)
        verifier_step = {
            "index": 5,
            "tool": verifier_tool,
            "invocation_id": verifier_id,
            "status": "passed" if not validation_errors else "failed",
            "wall_time_seconds": time.perf_counter() - started,
            "gpu": monitor.summary(),
            "validation_errors": validation_errors,
            "result": verifier_result,
        }
        report["steps"].append(verifier_step)
        print(json.dumps({key: verifier_step[key] for key in ("tool", "status", "wall_time_seconds", "gpu")}), flush=True)
        if validation_errors:
            raise RuntimeError(f"Verifier output contract failed: {validation_errors}")
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        print(json.dumps(report["error"]), flush=True)
    finally:
        report["finished_at"] = _utc_now()
        _write_state(output_dir, report)
        latest_path = Path(args.output_dir).resolve() / "LATEST_RUN.txt"
        latest_path.write_text(str(output_dir) + "\n", encoding="utf-8")

    return 0 if report["status"] == "passed" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run serial real-expert smoke calls through the control plane.")
    parser.add_argument("--base-url", default="http://127.0.0.1:28080")
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--output-dir",
        default="runs/hydro_remote_agent/real_expert_smoke_v1",
    )
    parser.add_argument("--run-id")
    parser.add_argument("--gpu-id", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    return parser


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
