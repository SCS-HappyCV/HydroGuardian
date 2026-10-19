from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class ExperimentLedgerError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _lookup(payload: Mapping[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise KeyError(dotted_path)
        value = value[part]
    return value


def _observed_count(report: Mapping[str, Any]) -> int | None:
    for path in (
        "metrics.count",
        "completed_count",
        "input_count",
        "gold_count",
        "job_count",
    ):
        try:
            value = _lookup(report, path)
        except KeyError:
            continue
        if isinstance(value, int):
            return value
    return None


def collect_experiment_ledger(
    protocol_path: str | Path,
    project_root: str | Path,
) -> dict[str, Any]:
    protocol_path = Path(protocol_path).resolve()
    project_root = Path(project_root).resolve()
    with protocol_path.open("r", encoding="utf-8") as handle:
        protocol = json.load(handle)

    if protocol.get("schema_version") != "vague_hydro.experiment_protocol.v1":
        raise ExperimentLedgerError("Unsupported experiment protocol schema")

    collected_runs: list[dict[str, Any]] = []
    for spec in protocol.get("runs", []):
        report_path = project_root / spec["report"]
        record: dict[str, Any] = {
            "run_id": spec["run_id"],
            "claim_ids": spec.get("claim_ids", []),
            "kind": spec["kind"],
            "role": spec["role"],
            "expected_count": spec["expected_count"],
            "report": spec["report"],
        }
        if spec.get("pending_dependency"):
            record["pending_dependency"] = spec["pending_dependency"]
        if not report_path.is_file():
            record.update(status="missing", reason="report_not_found")
            collected_runs.append(record)
            continue

        try:
            with report_path.open("r", encoding="utf-8") as handle:
                report = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            record.update(status="invalid", reason=str(exc))
            collected_runs.append(record)
            continue

        missing_metrics: list[str] = []
        metrics: dict[str, Any] = {}
        for metric_path in spec.get("metric_paths", []):
            try:
                metrics[metric_path] = _lookup(report, metric_path)
            except KeyError:
                missing_metrics.append(metric_path)
        observed_count = _observed_count(report)
        status = "completed"
        report_status = str(report.get("status", "")).lower()
        if report_status == "failed":
            status = "failed"
        elif missing_metrics:
            status = "invalid"
        elif observed_count is not None and observed_count != spec["expected_count"]:
            status = "count_mismatch"
        elif report_status == "partial":
            status = "partial"
        elif spec.get("pending_dependency"):
            status = "partial"

        record.update(
            status=status,
            observed_count=observed_count,
            report_sha256=_sha256(report_path),
            report_schema_version=report.get("schema_version"),
            metrics=metrics,
        )
        if missing_metrics:
            record["missing_metrics"] = missing_metrics
        collected_runs.append(record)

    status_counts: dict[str, int] = {}
    for run in collected_runs:
        status_counts[run["status"]] = status_counts.get(run["status"], 0) + 1
    return {
        "schema_version": "vague_hydro.experiment_ledger.v1",
        "protocol_id": protocol["protocol_id"],
        "collected_at": _utc_now(),
        "protocol_path": str(protocol_path),
        "protocol_sha256": _sha256(protocol_path),
        "split": protocol["split"],
        "claims": protocol["claims"],
        "status_counts": status_counts,
        "runs": collected_runs,
    }


def write_experiment_ledger(ledger: Mapping[str, Any], output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / "experiment_ledger.json"
    missing_path = output_dir / "missing_runs.json"
    with ledger_path.open("w", encoding="utf-8") as handle:
        json.dump(ledger, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    incomplete = [run for run in ledger["runs"] if run["status"] != "completed"]
    with missing_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "schema_version": "vague_hydro.missing_runs.v1",
                "protocol_id": ledger["protocol_id"],
                "runs": incomplete,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )
        handle.write("\n")
