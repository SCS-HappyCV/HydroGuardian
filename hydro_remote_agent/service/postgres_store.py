from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from .contracts import JOB_STATUSES, JobRecord, JobSubmission, STEP_STATUSES, StepRecord


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostgresJobStore:
    """PostgreSQL job queue with transactional leases and audit events."""

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL storage requires psycopg") from exc
        self.database_url = database_url
        self._psycopg = psycopg
        self._row_factory = dict_row
        self.initialize()

    @contextmanager
    def _session(self):
        with self._psycopg.connect(self.database_url, row_factory=self._row_factory) as connection:
            with connection.transaction():
                yield connection

    def initialize(self) -> None:
        with self._session() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    status TEXT NOT NULL,
                    submission_json JSONB NOT NULL,
                    plan_json JSONB,
                    result_json JSONB,
                    error_json JSONB,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_expires_at DOUBLE PRECISION,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
                CREATE TABLE IF NOT EXISTS job_events (
                    event_id BIGSERIAL PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    event_type TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT,
                    payload_json JSONB NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id, event_id);
                CREATE TABLE IF NOT EXISTS workflow_steps (
                    step_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    tool TEXT NOT NULL, status TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 1,
                    worker_id TEXT, progress DOUBLE PRECISION NOT NULL DEFAULT 0, phase TEXT NOT NULL DEFAULT '',
                    arguments_json JSONB NOT NULL DEFAULT '{}'::jsonb, result_json JSONB, error_json JSONB,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workflow_steps_job ON workflow_steps(job_id, updated_at);
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_id TEXT PRIMARY KEY, worker_id TEXT NOT NULL, message_type TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                );
                """
            )

    def create_job(self, submission: JobSubmission, idempotency_key: Optional[str] = None) -> JobRecord:
        key = idempotency_key.strip() if idempotency_key else None
        if key:
            existing = self.get_by_idempotency_key(key)
            if existing is not None:
                return existing
        job_id = f"job_{uuid.uuid4().hex}"
        trace_id = f"trace_{uuid.uuid4().hex}"
        status = "queued_execution" if submission.planned_request else "queued_planning"
        now = _utc_now()
        with self._session() as connection:
            row = connection.execute(
                """INSERT INTO jobs(job_id, request_id, trace_id, idempotency_key, status,
                   submission_json, plan_json, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (idempotency_key) DO NOTHING RETURNING job_id""",
                (job_id, submission.request_id, trace_id, key, status,
                 json.dumps(submission.to_dict()),
                 json.dumps(submission.planned_request) if submission.planned_request else None,
                 now, now),
            ).fetchone()
            if row is not None:
                self._event(connection, job_id, "created", None, status, {})
        if row is None and key:
            existing = self.get_by_idempotency_key(key)
            if existing is not None:
                return existing
        return self.require(job_id)

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._session() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=%s", (job_id,)).fetchone()
        return self._record(row) if row else None

    def require(self, job_id: str) -> JobRecord:
        record = self.get(job_id)
        if record is None:
            raise KeyError(f"Unknown job {job_id!r}")
        return record

    def get_by_idempotency_key(self, key: str) -> Optional[JobRecord]:
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE idempotency_key=%s", (key,)
            ).fetchone()
        return self._record(row) if row else None

    def list_jobs(self, limit: int = 100, status: Optional[str] = None) -> List[JobRecord]:
        if status is not None and status not in JOB_STATUSES:
            raise ValueError(f"Unsupported job status {status!r}")
        query = "SELECT * FROM jobs"
        params: list[Any] = []
        if status:
            query += " WHERE status=%s"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(max(1, min(int(limit), 1000)))
        with self._session() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._record(row) for row in rows]

    def claim(self, stage: str, owner: str, lease_seconds: float = 300.0) -> Optional[JobRecord]:
        stages = {"planning": ("queued_planning", "planning"), "execution": ("queued_execution", "executing")}
        if stage not in stages:
            raise ValueError("stage must be planning or execution")
        queued, active = stages[stage]
        now = _utc_now()
        with self._session() as connection:
            row = connection.execute(
                "SELECT job_id FROM jobs WHERE status=%s ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1",
                (queued,),
            ).fetchone()
            if row is None:
                return None
            job_id = str(row["job_id"])
            connection.execute(
                """UPDATE jobs SET status=%s, attempts=attempts+1, lease_owner=%s,
                   lease_expires_at=%s, updated_at=%s, version=version+1 WHERE job_id=%s""",
                (active, owner, time.time() + max(float(lease_seconds), 1.0), now, job_id),
            )
            self._event(connection, job_id, "claimed", queued, active, {"owner": owner})
        return self.require(job_id)

    def transition(self, job_id: str, expected_status: str, new_status: str, *,
                   plan: Optional[Mapping[str, Any]] = None,
                   result: Optional[Mapping[str, Any]] = None,
                   error: Optional[Mapping[str, Any]] = None,
                   event_type: str = "transitioned") -> JobRecord:
        if expected_status not in JOB_STATUSES or new_status not in JOB_STATUSES:
            raise ValueError("Unsupported job status transition")
        assignments = ["status=%s", "lease_owner=NULL", "lease_expires_at=NULL", "updated_at=%s", "version=version+1"]
        values: list[Any] = [new_status, _utc_now()]
        for column, value in (("plan_json", plan), ("result_json", result), ("error_json", error)):
            if value is not None:
                assignments.append(f"{column}=%s")
                values.append(json.dumps(dict(value)))
        values.extend([job_id, expected_status])
        with self._session() as connection:
            cursor = connection.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE job_id=%s AND status=%s", values
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Job {job_id!r} is no longer in expected status {expected_status!r}")
            self._event(connection, job_id, event_type, expected_status, new_status, dict(error or {}))
        return self.require(job_id)

    def recover_expired(self, now: Optional[float] = None) -> int:
        now_epoch = time.time() if now is None else float(now)
        recovered = 0
        expired_job_ids: list[str] = []
        with self._session() as connection:
            rows = connection.execute(
                """SELECT job_id, status FROM jobs WHERE status IN ('planning', 'executing')
                   AND lease_expires_at IS NOT NULL AND lease_expires_at < %s FOR UPDATE SKIP LOCKED""",
                (now_epoch,),
            ).fetchall()
            for row in rows:
                old = str(row["status"])
                new = "queued_planning" if old == "planning" else "queued_execution"
                connection.execute(
                    """UPDATE jobs SET status=%s, lease_owner=NULL, lease_expires_at=NULL,
                       updated_at=%s, version=version+1 WHERE job_id=%s""",
                    (new, _utc_now(), row["job_id"]),
                )
                self._event(connection, str(row["job_id"]), "lease_recovered", old, new, {})
                expired_job_ids.append(str(row["job_id"]))
                recovered += 1
        for job_id in expired_job_ids:
            self.mark_lost_steps(job_id=job_id)
        return recovered

    def mark_lost_steps(self, worker_id: Optional[str] = None, job_id: Optional[str] = None) -> int:
        query = "SELECT step_id, job_id, tool, worker_id FROM workflow_steps WHERE status IN ('dispatched', 'running')"
        params: list[Any] = []
        if worker_id:
            query += " AND worker_id=%s"
            params.append(worker_id)
        if job_id:
            query += " AND job_id=%s"
            params.append(job_id)
        with self._session() as connection:
            rows = connection.execute(query, params).fetchall()
            for row in rows:
                error = {"code": "worker_disconnected", "worker_id": row["worker_id"]}
                connection.execute(
                    "UPDATE workflow_steps SET status='lost', error_json=%s, updated_at=%s WHERE step_id=%s AND status IN ('dispatched', 'running')",
                    (json.dumps(error), _utc_now(), row["step_id"]),
                )
                self._event(connection, row["job_id"], "step_lost", None, None, {
                    "step_id": row["step_id"], "tool": row["tool"], "error": error,
                })
            return len(rows)

    def cancel(self, job_id: str) -> JobRecord:
        job = self.require(job_id)
        if job.status not in {"queued_planning", "queued_execution"}:
            raise ValueError("Only queued jobs can be cancelled")
        return self.transition(job_id, job.status, "cancelled", event_type="cancelled")

    def retry(self, job_id: str) -> JobRecord:
        job = self.require(job_id)
        if job.status not in {"failed", "blocked_expert"}:
            raise ValueError("Only failed or blocked jobs can be retried")
        new_status = "queued_execution" if job.plan is not None else "queued_planning"
        with self._session() as connection:
            cursor = connection.execute(
                """UPDATE jobs SET status=%s, result_json=NULL, error_json=NULL,
                   lease_owner=NULL, lease_expires_at=NULL, updated_at=%s, version=version+1
                   WHERE job_id=%s AND status=%s""",
                (new_status, _utc_now(), job_id, job.status),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Job status changed while retrying")
            self._event(connection, job_id, "retried", job.status, new_status, {})
        return self.require(job_id)

    def events(self, job_id: str) -> List[Dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM job_events WHERE job_id=%s ORDER BY event_id", (job_id,)
            ).fetchall()
        return [{
            "event_id": int(row["event_id"]), "event_type": row["event_type"],
            "from_status": row["from_status"], "to_status": row["to_status"],
            "payload": self._json_value(row["payload_json"]), "created_at": row["created_at"],
        } for row in rows]

    def upsert_step(self, step_id: str, job_id: str, tool: str, *, status: str = "dispatched",
                    attempt: int = 1, worker_id: Optional[str] = None, progress: float = 0.0,
                    phase: str = "", arguments: Optional[Mapping[str, Any]] = None,
                    result: Optional[Mapping[str, Any]] = None, error: Optional[Mapping[str, Any]] = None) -> StepRecord:
        if status not in STEP_STATUSES:
            raise ValueError(f"Unsupported step status {status!r}")
        now = _utc_now()
        with self._session() as connection:
            connection.execute("""INSERT INTO workflow_steps(step_id, job_id, tool, status, attempt, worker_id,
                progress, phase, arguments_json, result_json, error_json, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(step_id) DO UPDATE SET status=EXCLUDED.status, attempt=EXCLUDED.attempt,
                worker_id=EXCLUDED.worker_id, progress=EXCLUDED.progress, phase=EXCLUDED.phase,
                arguments_json=EXCLUDED.arguments_json, result_json=EXCLUDED.result_json,
                error_json=EXCLUDED.error_json, updated_at=EXCLUDED.updated_at""",
                (step_id, job_id, tool, status, int(attempt), worker_id, float(progress), phase,
                 json.dumps(dict(arguments or {})), json.dumps(dict(result)) if result is not None else None,
                 json.dumps(dict(error)) if error is not None else None, now))
        return self.step(step_id)

    def step(self, step_id: str) -> StepRecord:
        with self._session() as connection:
            row = connection.execute("SELECT * FROM workflow_steps WHERE step_id=%s", (step_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown step {step_id!r}")
        return StepRecord(step_id=row["step_id"], job_id=row["job_id"], tool=row["tool"], status=row["status"],
            attempt=int(row["attempt"]), worker_id=row["worker_id"], progress=float(row["progress"]),
            phase=row["phase"], arguments=self._json_value(row["arguments_json"]),
            result=self._json_value(row["result_json"]), error=self._json_value(row["error_json"]),
            updated_at=str(row["updated_at"]))

    def steps(self, job_id: str) -> List[StepRecord]:
        with self._session() as connection:
            rows = connection.execute("SELECT step_id FROM workflow_steps WHERE job_id=%s ORDER BY updated_at", (job_id,)).fetchall()
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
                    "INSERT INTO processed_messages(message_id, worker_id, message_type, processed_at) VALUES (%s, %s, %s, %s)",
                    (message_id, worker_id, message_type, _utc_now()),
                )
            return True
        except self._psycopg.errors.UniqueViolation:
            return False

    def recoverable_steps(self) -> List[StepRecord]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT step_id FROM workflow_steps WHERE status='lost' ORDER BY updated_at"
            ).fetchall()
        return [self.step(str(row["step_id"])) for row in rows]

    @staticmethod
    def _event(connection: Any, job_id: str, event_type: str, from_status: Optional[str],
               to_status: Optional[str], payload: Mapping[str, Any]) -> None:
        connection.execute(
            """INSERT INTO job_events(job_id, event_type, from_status, to_status, payload_json, created_at)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (job_id, event_type, from_status, to_status, json.dumps(dict(payload)), _utc_now()),
        )

    @staticmethod
    def _json_value(value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    @classmethod
    def _record(cls, row: Mapping[str, Any]) -> JobRecord:
        return JobRecord(
            job_id=str(row["job_id"]), request_id=str(row["request_id"]), trace_id=str(row["trace_id"]),
            status=str(row["status"]), submission=cls._json_value(row["submission_json"]) or {},
            plan=cls._json_value(row["plan_json"]), result=cls._json_value(row["result_json"]),
            error=cls._json_value(row["error_json"]), attempts=int(row["attempts"]),
            lease_owner=row["lease_owner"], lease_expires_at=row["lease_expires_at"],
            created_at=str(row["created_at"]), updated_at=str(row["updated_at"]), version=int(row["version"]),
        )
