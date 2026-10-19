from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .contracts import JOB_STATUSES, JobRecord, JobSubmission, STEP_STATUSES, StepRecord


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class JobStore:
    """SQLite-backed Agent job queue with atomic leases and an event audit log."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def _session(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._session() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    status TEXT NOT NULL,
                    submission_json TEXT NOT NULL,
                    plan_json TEXT,
                    result_json TEXT,
                    error_json TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_expires_at REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_status_created
                    ON jobs(status, created_at);
                CREATE TABLE IF NOT EXISTS job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    event_type TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_job_events_job
                    ON job_events(job_id, event_id);
                CREATE TABLE IF NOT EXISTS workflow_steps (
                    step_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    tool TEXT NOT NULL, status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 1,
                    worker_id TEXT, progress REAL NOT NULL DEFAULT 0, phase TEXT NOT NULL DEFAULT '',
                    arguments_json TEXT NOT NULL DEFAULT '{}', result_json TEXT, error_json TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workflow_steps_job ON workflow_steps(job_id, updated_at);
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, message_type TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                );
                """
            )

    def create_job(
        self,
        submission: JobSubmission,
        idempotency_key: Optional[str] = None,
    ) -> JobRecord:
        key = idempotency_key.strip() if idempotency_key else None
        if key:
            existing = self.get_by_idempotency_key(key)
            if existing is not None:
                return existing
        job_id = f"job_{uuid.uuid4().hex}"
        trace_id = f"trace_{uuid.uuid4().hex}"
        status = "queued_execution" if submission.planned_request else "queued_planning"
        now = _utc_now()
        try:
            with self._session() as connection:
                connection.execute(
                    """INSERT INTO jobs(
                        job_id, request_id, trace_id, idempotency_key, status,
                        submission_json, plan_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job_id,
                        submission.request_id,
                        trace_id,
                        key,
                        status,
                        _json(submission.to_dict()),
                        _json(submission.planned_request) if submission.planned_request else None,
                        now,
                        now,
                    ),
                )
                self._event(connection, job_id, "created", None, status, {})
        except sqlite3.IntegrityError:
            if key:
                existing = self.get_by_idempotency_key(key)
                if existing is not None:
                    return existing
            raise
        return self.require(job_id)

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return self._record(row) if row is not None else None

    def require(self, job_id: str) -> JobRecord:
        record = self.get(job_id)
        if record is None:
            raise KeyError(f"Unknown job {job_id!r}")
        return record

    def get_by_idempotency_key(self, key: str) -> Optional[JobRecord]:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE idempotency_key=?", (key,)
            ).fetchone()
        return self._record(row) if row is not None else None

    def list_jobs(self, limit: int = 100, status: Optional[str] = None) -> List[JobRecord]:
        if status is not None and status not in JOB_STATUSES:
            raise ValueError(f"Unsupported job status {status!r}")
        query = "SELECT * FROM jobs"
        params: List[Any] = []
        if status:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with self._session() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._record(row) for row in rows]

    def claim(self, stage: str, owner: str, lease_seconds: float = 300.0) -> Optional[JobRecord]:
        stages = {
            "planning": ("queued_planning", "planning"),
            "execution": ("queued_execution", "executing"),
        }
        if stage not in stages:
            raise ValueError("stage must be planning or execution")
        queued, active = stages[stage]
        now_epoch = time.time()
        now = _utc_now()
        with self._session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT job_id FROM jobs WHERE status=? ORDER BY created_at LIMIT 1",
                (queued,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            job_id = str(row["job_id"])
            updated = connection.execute(
                """UPDATE jobs SET status=?, attempts=attempts+1, lease_owner=?,
                    lease_expires_at=?, updated_at=?, version=version+1
                    WHERE job_id=? AND status=?""",
                (active, owner, now_epoch + max(float(lease_seconds), 1.0), now, job_id, queued),
            ).rowcount
            if updated != 1:
                connection.rollback()
                return None
            self._event(connection, job_id, "claimed", queued, active, {"owner": owner})
            connection.commit()
        return self.require(job_id)

    def transition(
        self,
        job_id: str,
        expected_status: str,
        new_status: str,
        *,
        plan: Optional[Mapping[str, Any]] = None,
        result: Optional[Mapping[str, Any]] = None,
        error: Optional[Mapping[str, Any]] = None,
        event_type: str = "transitioned",
    ) -> JobRecord:
        if expected_status not in JOB_STATUSES or new_status not in JOB_STATUSES:
            raise ValueError("Unsupported job status transition")
        assignments = [
            "status=?",
            "lease_owner=NULL",
            "lease_expires_at=NULL",
            "updated_at=?",
            "version=version+1",
        ]
        values: List[Any] = [new_status, _utc_now()]
        for column, value in (("plan_json", plan), ("result_json", result), ("error_json", error)):
            if value is not None:
                assignments.append(f"{column}=?")
                values.append(_json(dict(value)))
        values.extend([job_id, expected_status])
        with self._session() as connection:
            updated = connection.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE job_id=? AND status=?",
                values,
            ).rowcount
            if updated != 1:
                raise RuntimeError(
                    f"Job {job_id!r} is no longer in expected status {expected_status!r}"
                )
            self._event(
                connection,
                job_id,
                event_type,
                expected_status,
                new_status,
                dict(error or {}),
            )
        return self.require(job_id)

    def recover_expired(self, now: Optional[float] = None) -> int:
        now_epoch = time.time() if now is None else float(now)
        recovered = 0
        expired_job_ids: list[str] = []
        with self._session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """SELECT job_id, status FROM jobs
                   WHERE status IN ('planning', 'executing')
                     AND lease_expires_at IS NOT NULL AND lease_expires_at < ?""",
                (now_epoch,),
            ).fetchall()
            for row in rows:
                old = str(row["status"])
                new = "queued_planning" if old == "planning" else "queued_execution"
                connection.execute(
                    """UPDATE jobs SET status=?, lease_owner=NULL, lease_expires_at=NULL,
                       updated_at=?, version=version+1 WHERE job_id=?""",
                    (new, _utc_now(), row["job_id"]),
                )
                self._event(connection, str(row["job_id"]), "lease_recovered", old, new, {})
                expired_job_ids.append(str(row["job_id"]))
                recovered += 1
            connection.commit()
        for job_id in expired_job_ids:
            self.mark_lost_steps(job_id=job_id)
        return recovered

    def mark_lost_steps(self, worker_id: Optional[str] = None, job_id: Optional[str] = None) -> int:
        query = "SELECT step_id, job_id, tool, attempt, worker_id, progress, phase, arguments_json FROM workflow_steps WHERE status IN ('dispatched', 'running')"
        params: list[Any] = []
        if worker_id:
            query += " AND worker_id=?"
            params.append(worker_id)
        if job_id:
            query += " AND job_id=?"
            params.append(job_id)
        with self._session() as connection:
            rows = connection.execute(query, params).fetchall()
            for row in rows:
                error = {"code": "worker_disconnected", "worker_id": row["worker_id"]}
                connection.execute(
                    "UPDATE workflow_steps SET status='lost', error_json=?, updated_at=? WHERE step_id=? AND status IN ('dispatched', 'running')",
                    (_json(error), _utc_now(), row["step_id"]),
                )
                self._event(connection, row["job_id"], "step_lost", None, None, {
                    "step_id": row["step_id"], "tool": row["tool"], "error": error,
                })
            return len(rows)

    def cancel(self, job_id: str) -> JobRecord:
        job = self.require(job_id)
        if job.status not in {"queued_planning", "queued_execution"}:
            raise ValueError("Only queued jobs can be cancelled")
        return self.transition(
            job_id,
            job.status,
            "cancelled",
            event_type="cancelled",
        )

    def retry(self, job_id: str) -> JobRecord:
        job = self.require(job_id)
        if job.status not in {"failed", "blocked_expert"}:
            raise ValueError("Only failed or blocked jobs can be retried")
        new_status = "queued_execution" if job.plan is not None else "queued_planning"
        with self._session() as connection:
            updated = connection.execute(
                """UPDATE jobs SET status=?, result_json=NULL, error_json=NULL,
                    lease_owner=NULL, lease_expires_at=NULL, updated_at=?, version=version+1
                    WHERE job_id=? AND status=?""",
                (new_status, _utc_now(), job_id, job.status),
            ).rowcount
            if updated != 1:
                raise RuntimeError("Job status changed while retrying")
            self._event(connection, job_id, "retried", job.status, new_status, {})
        return self.require(job_id)

    def events(self, job_id: str) -> List[Dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM job_events WHERE job_id=? ORDER BY event_id", (job_id,)
            ).fetchall()
        return [
            {
                "event_id": int(row["event_id"]),
                "event_type": row["event_type"],
                "from_status": row["from_status"],
                "to_status": row["to_status"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def upsert_step(self, step_id: str, job_id: str, tool: str, *, status: str = "dispatched",
                    attempt: int = 1, worker_id: Optional[str] = None,
                    progress: float = 0.0, phase: str = "", arguments: Optional[Mapping[str, Any]] = None,
                    result: Optional[Mapping[str, Any]] = None, error: Optional[Mapping[str, Any]] = None) -> StepRecord:
        if status not in STEP_STATUSES:
            raise ValueError(f"Unsupported step status {status!r}")
        now = _utc_now()
        with self._session() as connection:
            connection.execute(
                """INSERT INTO workflow_steps(step_id, job_id, tool, status, attempt, worker_id, progress, phase,
                   arguments_json, result_json, error_json, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(step_id) DO UPDATE SET status=excluded.status, attempt=excluded.attempt,
                   worker_id=excluded.worker_id, progress=excluded.progress, phase=excluded.phase,
                   arguments_json=excluded.arguments_json, result_json=excluded.result_json,
                   error_json=excluded.error_json, updated_at=excluded.updated_at""",
                (step_id, job_id, tool, status, int(attempt), worker_id, float(progress), phase,
                 _json(dict(arguments or {})), _json(dict(result)) if result is not None else None,
                 _json(dict(error)) if error is not None else None, now),
            )
        return self.step(step_id)

    def step(self, step_id: str) -> StepRecord:
        with self._session() as connection:
            row = connection.execute("SELECT * FROM workflow_steps WHERE step_id=?", (step_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown step {step_id!r}")
        return StepRecord(step_id=row["step_id"], job_id=row["job_id"], tool=row["tool"], status=row["status"],
            attempt=int(row["attempt"]), worker_id=row["worker_id"], progress=float(row["progress"]),
            phase=row["phase"], arguments=json.loads(row["arguments_json"]),
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=json.loads(row["error_json"]) if row["error_json"] else None, updated_at=row["updated_at"])

    def steps(self, job_id: str) -> List[StepRecord]:
        with self._session() as connection:
            rows = connection.execute("SELECT step_id FROM workflow_steps WHERE job_id=? ORDER BY updated_at", (job_id,)).fetchall()
        return [self.step(str(row["step_id"])) for row in rows]

    def record_event(self, job_id: str, event_type: str, payload: Mapping[str, Any],
                     from_status: Optional[str] = None, to_status: Optional[str] = None) -> Dict[str, Any]:
        with self._session() as connection:
            self._event(connection, job_id, event_type, from_status, to_status, payload)
        return self.events(job_id)[-1]

    def claim_message(self, message_id: str, worker_id: str, message_type: str) -> bool:
        try:
            with self._session() as connection:
                connection.execute(
                    "INSERT INTO processed_messages(message_id, worker_id, message_type, processed_at) VALUES (?, ?, ?, ?)",
                    (message_id, worker_id, message_type, _utc_now()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def recoverable_steps(self) -> List[StepRecord]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT step_id FROM workflow_steps WHERE status='lost' ORDER BY updated_at"
            ).fetchall()
        return [self.step(str(row["step_id"])) for row in rows]

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        job_id: str,
        event_type: str,
        from_status: Optional[str],
        to_status: Optional[str],
        payload: Mapping[str, Any],
    ) -> None:
        connection.execute(
            """INSERT INTO job_events(
                job_id, event_type, from_status, to_status, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (job_id, event_type, from_status, to_status, _json(dict(payload)), _utc_now()),
        )

    @staticmethod
    def _record(row: sqlite3.Row) -> JobRecord:
        def decode(name: str) -> Optional[Dict[str, Any]]:
            value = row[name]
            return json.loads(value) if value is not None else None

        return JobRecord(
            job_id=str(row["job_id"]),
            request_id=str(row["request_id"]),
            trace_id=str(row["trace_id"]),
            status=str(row["status"]),
            submission=decode("submission_json") or {},
            plan=decode("plan_json"),
            result=decode("result_json"),
            error=decode("error_json"),
            attempts=int(row["attempts"]),
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            version=int(row["version"]),
        )
