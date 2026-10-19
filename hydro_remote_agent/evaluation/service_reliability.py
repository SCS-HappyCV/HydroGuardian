from __future__ import annotations

from typing import Any, Iterable, Mapping

import numpy as np


def latency_summary(values_ms: Iterable[float]) -> dict[str, Any]:
    values = np.asarray(list(values_ms), dtype=np.float64)
    if values.size == 0:
        return {"count": 0, "mean_ms": None, "p50_ms": None, "p95_ms": None, "max_ms": None}
    return {
        "count": int(values.size),
        "mean_ms": float(values.mean()),
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
        "max_ms": float(values.max()),
    }


def build_service_report(
    *,
    run_id: str,
    health_latencies_ms: Iterable[float],
    submission_latencies_ms: Iterable[float],
    end_to_end_latencies_ms: Iterable[float],
    jobs: Iterable[Mapping[str, Any]],
    checks: Mapping[str, bool],
    recovery: Mapping[str, Any],
) -> dict[str, Any]:
    jobs = list(jobs)
    status_counts: dict[str, int] = {}
    for job in jobs:
        status = str(job.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
    failed_checks = sorted(name for name, passed in checks.items() if not passed)
    return {
        "schema_version": "vague_hydro.service_reliability.v1",
        "run_id": run_id,
        "status": "passed" if not failed_checks else "failed",
        "job_count": len(jobs),
        "job_status_counts": status_counts,
        "metrics": {
            "health_latency": latency_summary(health_latencies_ms),
            "submission_latency": latency_summary(submission_latencies_ms),
            "end_to_end_latency": latency_summary(end_to_end_latencies_ms),
            "terminal_rate": (
                sum(status in {"succeeded", "blocked_expert", "failed", "cancelled"} for status in status_counts for _ in range(status_counts[status]))
                / len(jobs)
                if jobs
                else None
            ),
        },
        "checks": dict(checks),
        "failed_checks": failed_checks,
        "lease_recovery": dict(recovery),
    }
