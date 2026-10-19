from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


class TaskHistoryStore:
    def __init__(self, job_store: Any) -> None:
        self.job_store = job_store
        self.postgres = job_store.__class__.__name__ == "PostgresJobStore"
        self.placeholder = "%s" if self.postgres else "?"
        self.initialize()

    def initialize(self) -> None:
        json_type = "JSONB" if self.postgres else "TEXT"
        with self.job_store._session() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS task_records (
                    task_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
                    name TEXT NOT NULL,
                    input_text TEXT NOT NULL,
                    template_id TEXT,
                    zone_id TEXT,
                    scene_id TEXT,
                    sample_id TEXT,
                    priority TEXT NOT NULL DEFAULT 'medium',
                    created_by_user_id TEXT,
                    metadata_json {json_type} NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_records_created ON task_records(created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_records_zone ON task_records(zone_id, created_at)"
            )

    def upsert(self, job_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        job = self.job_store.require(job_id)
        task_id = self._required(payload, "task_id")
        input_text = str(payload.get("input_text") or job.submission.get("query") or "").strip()
        if not input_text:
            raise ValueError("input_text is required")
        name = str(payload.get("name") or input_text[:50] or "智能巡查任务").strip()
        priority = str(payload.get("priority") or "medium")
        if priority not in {"low", "medium", "high"}:
            raise ValueError("priority must be low, medium or high")
        now = _utc_now()
        values = (
            task_id, job_id, name, input_text, payload.get("template_id"), payload.get("zone_id"),
            payload.get("scene_id"), payload.get("sample_id"), priority, payload.get("created_by_user_id"),
            _json(dict(payload.get("metadata") or {})), job.created_at, now,
        )
        with self.job_store._session() as connection:
            if self.postgres:
                connection.execute(
                    """INSERT INTO task_records(task_id, job_id, name, input_text, template_id, zone_id,
                       scene_id, sample_id, priority, created_by_user_id, metadata_json, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT(task_id) DO UPDATE SET name=excluded.name, input_text=excluded.input_text,
                       template_id=excluded.template_id, zone_id=excluded.zone_id, scene_id=excluded.scene_id,
                       sample_id=excluded.sample_id, priority=excluded.priority,
                       created_by_user_id=excluded.created_by_user_id, metadata_json=excluded.metadata_json,
                       updated_at=excluded.updated_at""",
                    values,
                )
            else:
                connection.execute(
                    """INSERT INTO task_records(task_id, job_id, name, input_text, template_id, zone_id,
                       scene_id, sample_id, priority, created_by_user_id, metadata_json, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(task_id) DO UPDATE SET name=excluded.name, input_text=excluded.input_text,
                       template_id=excluded.template_id, zone_id=excluded.zone_id, scene_id=excluded.scene_id,
                       sample_id=excluded.sample_id, priority=excluded.priority,
                       created_by_user_id=excluded.created_by_user_id, metadata_json=excluded.metadata_json,
                       updated_at=excluded.updated_at""",
                    values,
                )
        return self.require(task_id)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self.job_store._session() as connection:
            row = connection.execute(
                f"SELECT * FROM task_records WHERE task_id={self.placeholder}", (task_id,)
            ).fetchone()
        return self._aggregate_row(row) if row else None

    def require(self, task_id: str) -> Dict[str, Any]:
        task = self.get(task_id)
        if task is None:
            raise KeyError(f"Unknown task {task_id!r}")
        return task

    def rebind_job(self, task_id: str, job_id: str, metadata: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        task = self.require(task_id)
        self.job_store.require(job_id)
        next_metadata = dict(task.get("metadata") or {})
        next_metadata.update(dict(metadata or {}))
        with self.job_store._session() as connection:
            connection.execute(
                f"UPDATE task_records SET job_id={self.placeholder}, metadata_json={self.placeholder}, updated_at={self.placeholder} WHERE task_id={self.placeholder}",
                (job_id, _json(next_metadata), _utc_now(), task_id),
            )
        return self.require(task_id)

    def list(self, *, limit: int = 100, status: Optional[str] = None, zone_id: Optional[str] = None, keyword: Optional[str] = None) -> list[Dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append(f"j.status={self.placeholder}")
            params.append(status)
        if zone_id:
            clauses.append(f"t.zone_id={self.placeholder}")
            params.append(zone_id)
        if keyword:
            clauses.append(f"(LOWER(t.name) LIKE {self.placeholder} OR LOWER(t.input_text) LIKE {self.placeholder} OR LOWER(t.task_id) LIKE {self.placeholder})")
            pattern = f"%{keyword.lower()}%"
            params.extend([pattern, pattern, pattern])
        query = "SELECT t.* FROM task_records t JOIN jobs j ON j.job_id=t.job_id"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += f" ORDER BY t.created_at DESC LIMIT {self.placeholder}"
        params.append(max(1, min(int(limit), 1000)))
        with self.job_store._session() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._aggregate_row(row) for row in rows]

    def history(self, task_id: str) -> Dict[str, Any]:
        task = self.require(task_id)
        job = self.job_store.require(task["job_id"])
        return {
            "task": task,
            "job": job.to_dict(),
            "steps": [step.to_dict() for step in self.job_store.steps(job.job_id)],
            "events": self.job_store.events(job.job_id),
            "artifacts": (job.result or {}).get("terminal_artifacts", {}),
        }

    def _aggregate_row(self, row: Any) -> Dict[str, Any]:
        job = self.job_store.require(str(row["job_id"]))
        result = job.result or {}
        risks = result.get("risk_candidates", []) if isinstance(result.get("risk_candidates", []), list) else []
        artifacts = result.get("terminal_artifacts", {}) if isinstance(result.get("terminal_artifacts", {}), dict) else {}
        steps = self.job_store.steps(job.job_id)
        workorder_count = self._count("workorders", "job_id", job.job_id)
        progress = self._progress(job.status, steps)
        return {
            "task_id": row["task_id"], "job_id": job.job_id, "request_id": job.request_id,
            "name": row["name"], "input_text": row["input_text"], "template_id": row["template_id"],
            "zone_id": row["zone_id"], "scene_id": row["scene_id"], "sample_id": row["sample_id"],
            "priority": row["priority"], "created_by_user_id": row["created_by_user_id"],
            "metadata": _decode(row["metadata_json"], {}), "job_status": job.status,
            "status": self._task_status(job.status), "progress": progress, "risk_count": len(risks),
            "workorder_count": workorder_count, "artifact_count": len(artifacts), "step_count": len(steps),
            "created_at": row["created_at"], "started_at": self._started_at(job, steps),
            "finished_at": job.updated_at if job.status in {"succeeded", "blocked_expert", "failed", "cancelled"} else None,
            "updated_at": job.updated_at,
        }

    def _count(self, table: str, column: str, value: str) -> int:
        try:
            with self.job_store._session() as connection:
                row = connection.execute(
                    f"SELECT COUNT(*) AS count FROM {table} WHERE {column}={self.placeholder}", (value,)
                ).fetchone()
            return int(row["count"])
        except Exception:
            return 0

    @staticmethod
    def _task_status(status: str) -> str:
        if status == "succeeded":
            return "success"
        if status in {"failed", "blocked_expert", "cancelled"}:
            return "failed"
        if status in {"planning", "executing"}:
            return "running"
        return "queued"

    @staticmethod
    def _progress(status: str, steps: list[Any]) -> int:
        if status in {"succeeded", "blocked_expert", "failed", "cancelled"}:
            return 100
        if status == "queued_planning":
            return 5
        if status == "planning":
            return 15
        if status == "queued_execution":
            return 25
        if steps:
            return max(30, min(95, round(sum(float(step.progress) for step in steps) / len(steps) * 100)))
        return 35

    @staticmethod
    def _started_at(job: Any, steps: list[Any]) -> Optional[str]:
        if steps:
            return min((step.updated_at for step in steps if step.updated_at), default=job.updated_at)
        return job.updated_at if job.status not in {"queued_planning", "queued_execution"} else None

    @staticmethod
    def _required(payload: Mapping[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} is required")
        return value.strip()
