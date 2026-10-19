from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hydro_remote_agent.evaluation.service_reliability import build_service_report  # noqa: E402
from hydro_remote_agent.service.contracts import JobSubmission  # noqa: E402
from hydro_remote_agent.service.store import JobStore  # noqa: E402


TERMINAL = {"succeeded", "blocked_expert", "failed", "cancelled"}


def _request(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], float]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        base_url.rstrip("/") + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            return response.status, result, (time.perf_counter() - started) * 1000.0
    except HTTPError as exc:
        content = exc.read().decode("utf-8")
        try:
            result = json.loads(content) if content else {}
        except json.JSONDecodeError:
            result = {"raw_error_body": content}
        return exc.code, result, (time.perf_counter() - started) * 1000.0
    except (TimeoutError, URLError, OSError) as exc:
        return (
            0,
            {"transport_error": f"{type(exc).__name__}: {exc}"},
            (time.perf_counter() - started) * 1000.0,
        )


def _direct_payload(run_id: str, index: int, image_path: str) -> dict[str, Any]:
    request_id = f"{run_id}:direct:{index:03d}"
    plan = {
        "schema_version": "1.0",
        "request_id": request_id,
        "intent": "class_presence",
        "action": {"type": "direct_answer", "answer": "Service reliability probe."},
        "expected_output": {"type": "text", "coordinate_space": "none"},
    }
    return {
        "request_id": request_id,
        "query": "Return the supplied deterministic probe response.",
        "language": "en",
        "assets": {"image_path": image_path},
        "planned_request": plan,
    }


def _blocked_payload(run_id: str, image_path: str, point_path: str) -> dict[str, Any]:
    request_id = f"{run_id}:blocked"
    return {
        "request_id": request_id,
        "query": "Segment the waterline described by this query.",
        "language": "en",
        "assets": {"image_path": image_path, "point_cloud_path": point_path},
        "planned_request": {
            "schema_version": "1.0",
            "request_id": request_id,
            "intent": "class_segmentation",
            "action": {
                "type": "tool_call",
                "tool": "language_guided_point_segmentation",
                "arguments": {
                    "image_path": image_path,
                    "point_cloud_path": point_path,
                    "query": "Segment the waterline.",
                    "target_class_ids": [13],
                },
            },
            "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
        },
    }


def _wait_terminal(base_url: str, job_ids: list[str], timeout_seconds: float) -> tuple[list[dict[str, Any]], dict[str, float]]:
    pending = set(job_ids)
    terminal: dict[str, dict[str, Any]] = {}
    finished_at: dict[str, float] = {}
    deadline = time.monotonic() + timeout_seconds
    while pending and time.monotonic() < deadline:
        for job_id in list(pending):
            status, job, _ = _request(base_url, "GET", f"/v1/jobs/{job_id}")
            if status == 200 and job.get("status") in TERMINAL:
                terminal[job_id] = job
                finished_at[job_id] = time.perf_counter()
                pending.remove(job_id)
        if pending:
            time.sleep(0.1)
    for job_id in pending:
        status, job, _ = _request(base_url, "GET", f"/v1/jobs/{job_id}")
        terminal[job_id] = job if status == 200 else {"job_id": job_id, "status": "unavailable"}
    return [terminal[job_id] for job_id in job_ids], finished_at


def _lease_recovery_probe() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temp_dir:
        store = JobStore(Path(temp_dir) / "jobs.sqlite")
        plan = {
            "schema_version": "1.0",
            "request_id": "lease-probe",
            "intent": "class_presence",
            "action": {"type": "direct_answer", "answer": "probe"},
            "expected_output": {"type": "text", "coordinate_space": "none"},
        }
        job = store.create_job(
            JobSubmission(
                request_id="lease-probe",
                query="probe",
                assets={"image_path": "/tmp/probe.png"},
                planned_request=plan,
            )
        )
        claimed = store.claim("execution", "crashed-worker", lease_seconds=1.0)
        recovered_count = store.recover_expired(now=time.time() + 2.0)
        recovered = store.require(job.job_id)
        events = store.events(job.job_id)
        return {
            "mode": "isolated_sqlite_store",
            "claimed": claimed is not None and claimed.status == "executing",
            "recovered_count": recovered_count,
            "final_status": recovered.status,
            "lease_recovered_event": any(event["event_type"] == "lease_recovered" for event in events),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the deployed VagueHydro Agent service.")
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--health-requests", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--run-id", default=f"service-{uuid.uuid4().hex[:12]}")
    parser.add_argument("--image-path", required=True)
    parser.add_argument("--point-path", required=True)
    args = parser.parse_args()
    if args.jobs < 1 or args.concurrency < 1 or args.health_requests < 1:
        raise ValueError("jobs, concurrency, and health-requests must be positive")

    health_latencies = []
    health_ok = True
    for _ in range(args.health_requests):
        status, payload, latency = _request(args.base_url, "GET", "/healthz")
        health_latencies.append(latency)
        health_ok &= status == 200 and payload.get("status") == "ok"

    invalid_status, _, _ = _request(args.base_url, "POST", "/v1/jobs", {"query": "missing id"})
    unknown_status, _, _ = _request(args.base_url, "GET", "/v1/jobs/job_does_not_exist")

    probe = _direct_payload(args.run_id, 9999, args.image_path)
    key = f"{args.run_id}:idempotency"
    first_status, first, _ = _request(
        args.base_url, "POST", "/v1/jobs", probe, {"Idempotency-Key": key}
    )
    second_status, second, _ = _request(
        args.base_url, "POST", "/v1/jobs", probe, {"Idempotency-Key": key}
    )

    payloads = [_direct_payload(args.run_id, index, args.image_path) for index in range(args.jobs)]
    submitted_at: dict[str, float] = {}

    def submit(payload: dict[str, Any]) -> tuple[int, dict[str, Any], float, float]:
        started = time.perf_counter()
        status, job, latency = _request(
            args.base_url,
            "POST",
            "/v1/jobs",
            payload,
            {"Idempotency-Key": payload["request_id"]},
        )
        return status, job, latency, started

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        submissions = list(pool.map(submit, payloads))
    submission_latencies = [item[2] for item in submissions]
    job_ids = []
    submissions_ok = True
    for status, job, _, started in submissions:
        submissions_ok &= status == 202 and "job_id" in job
        if "job_id" in job:
            job_ids.append(str(job["job_id"]))
            submitted_at[str(job["job_id"])] = started
    jobs, finished_at = _wait_terminal(args.base_url, job_ids, args.timeout_seconds)
    end_to_end = [
        (finished_at[job_id] - submitted_at[job_id]) * 1000.0
        for job_id in job_ids
        if job_id in finished_at
    ]
    direct_succeeded = len(jobs) == args.jobs and all(job.get("status") == "succeeded" for job in jobs)
    event_chains_ok = True
    for job_id in job_ids:
        status, payload, _ = _request(args.base_url, "GET", f"/v1/jobs/{job_id}/events")
        event_types = [event.get("event_type") for event in payload.get("events", [])]
        event_chains_ok &= status == 200 and event_types == ["created", "claimed", "execution_succeeded"]

    blocked_status, blocked_job, _ = _request(
        args.base_url,
        "POST",
        "/v1/jobs",
        _blocked_payload(args.run_id, args.image_path, args.point_path),
        {"Idempotency-Key": f"{args.run_id}:blocked"},
    )
    blocked_jobs, _ = _wait_terminal(args.base_url, [str(blocked_job.get("job_id"))], args.timeout_seconds)
    blocked = blocked_jobs[0]
    retry_status, retried, _ = _request(
        args.base_url, "POST", f"/v1/jobs/{blocked.get('job_id')}/retry", {}
    )
    retried_jobs, _ = _wait_terminal(args.base_url, [str(blocked.get("job_id"))], args.timeout_seconds)
    retried_final = retried_jobs[0]

    recovery = _lease_recovery_probe()
    checks = {
        "health_all_ok": health_ok,
        "invalid_request_rejected": invalid_status == 422,
        "unknown_job_returns_404": unknown_status == 404,
        "idempotency_returns_same_job": (
            first_status == second_status == 202 and first.get("job_id") == second.get("job_id")
        ),
        "concurrent_submissions_accepted": submissions_ok and len(job_ids) == args.jobs,
        "direct_jobs_succeeded": direct_succeeded,
        "event_chains_complete": event_chains_ok,
        "mock_expert_blocked": blocked_status == 202 and blocked.get("status") == "blocked_expert",
        "blocked_job_retryable": retry_status == 202 and retried.get("status") == "queued_execution",
        "blocked_job_reblocked": retried_final.get("status") == "blocked_expert" and int(retried_final.get("attempts", 0)) >= 2,
        "lease_recovery_passed": (
            recovery["claimed"]
            and recovery["recovered_count"] == 1
            and recovery["final_status"] == "queued_execution"
            and recovery["lease_recovered_event"]
        ),
    }
    all_jobs = [*jobs, blocked, retried_final]
    report = build_service_report(
        run_id=args.run_id,
        health_latencies_ms=health_latencies,
        submission_latencies_ms=submission_latencies,
        end_to_end_latencies_ms=end_to_end,
        jobs=all_jobs,
        checks=checks,
        recovery=recovery,
    )
    report["configuration"] = {
        "base_url": args.base_url,
        "direct_jobs": args.jobs,
        "concurrency": args.concurrency,
        "health_requests": args.health_requests,
    }
    submission_status_counts: dict[str, int] = {}
    for status, _, _, _ in submissions:
        key = str(status)
        submission_status_counts[key] = submission_status_counts.get(key, 0) + 1
    report["http_statuses"] = {
        "concurrent_submissions": submission_status_counts,
        "invalid_request": invalid_status,
        "unknown_job": unknown_status,
        "idempotency_first": first_status,
        "idempotency_second": second_status,
        "blocked_submission": blocked_status,
        "blocked_retry": retry_status,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"SERVICE_RELIABILITY_DONE status={report['status']} jobs={args.jobs} "
        f"failed_checks={len(report['failed_checks'])} output={args.output}"
    )
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
