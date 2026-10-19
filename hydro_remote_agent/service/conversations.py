from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


MESSAGE_ROLES = {"user", "assistant", "system"}
MESSAGE_INTENTS = {"ask", "append_context", "workflow_patch", "replan", "cancel", "status"}

STATUS_QUERY_TERMS = (
    "状态", "进度", "到哪", "完成没", "完成了", "结束没", "还要多久", "多久", "结果", "产物",
    "谁在", "哪个专家", "是否在线", "有没有", "为什么", "怎么了", "异常", "失败", "成功",
)
CONTEXT_TERMS = (
    "重点", "关注", "排除", "忽略", "范围", "区域", "优先", "只看", "不要", "需要", "补充",
    "限定", "阈值", "水线", "岸线", "道路", "现场", "改为", "调整为",
)


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


def infer_message_intent(content: str) -> tuple[str, Dict[str, Any]]:
    normalized = "".join(str(content).strip().lower().split())
    status_hits = [term for term in STATUS_QUERY_TERMS if term in normalized]
    context_hits = [term for term in CONTEXT_TERMS if term in normalized]
    question_form = normalized.endswith(("?", "？", "吗", "么", "呢"))
    if question_form or status_hits:
        intent = "ask"
        matched = status_hits or ["question_form"]
    elif context_hits:
        intent = "append_context"
        matched = context_hits
    else:
        intent = "ask"
        matched = ["safe_default"]
    return intent, {
        "classified_by": "semantic_router_v1",
        "matched_signals": matched,
        "confidence": "high" if question_form or len(matched) > 1 else "medium",
    }


class JobConversationStore:
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
                CREATE TABLE IF NOT EXISTS job_messages (
                    message_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    role TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json {json_type} NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_messages_job ON job_messages(job_id, created_at)"
            )

    def add(
        self,
        job_id: str,
        role: str,
        intent: str,
        content: str,
        *,
        metadata: Optional[Mapping[str, Any]] = None,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.job_store.require(job_id)
        role = str(role).strip()
        intent = str(intent).strip()
        content = str(content).strip()
        if role not in MESSAGE_ROLES:
            raise ValueError("role must be user, assistant or system")
        if intent not in MESSAGE_INTENTS:
            raise ValueError("Unsupported message intent")
        if not content:
            raise ValueError("content is required")
        if len(content) > 4000:
            raise ValueError("content must not exceed 4000 characters")
        identifier = message_id.strip() if isinstance(message_id, str) and message_id.strip() else f"msg_{uuid.uuid4().hex}"
        now = _utc_now()
        values = (identifier, job_id, role, intent, content, _json(dict(metadata or {})), now)
        with self.job_store._session() as connection:
            if self.postgres:
                connection.execute(
                    """INSERT INTO job_messages(message_id, job_id, role, intent, content, metadata_json, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT(message_id) DO NOTHING""",
                    values,
                )
            else:
                connection.execute(
                    """INSERT OR IGNORE INTO job_messages(message_id, job_id, role, intent, content, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
        return self.require(identifier)

    def require(self, message_id: str) -> Dict[str, Any]:
        with self.job_store._session() as connection:
            row = connection.execute(
                f"SELECT * FROM job_messages WHERE message_id={self.placeholder}", (message_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown message {message_id!r}")
        return self._row(row)

    def list(self, job_id: str, *, limit: int = 500) -> list[Dict[str, Any]]:
        self.job_store.require(job_id)
        with self.job_store._session() as connection:
            rows = connection.execute(
                f"SELECT * FROM job_messages WHERE job_id={self.placeholder} ORDER BY created_at, message_id LIMIT {self.placeholder}",
                (job_id, max(1, min(int(limit), 1000))),
            ).fetchall()
        return [self._row(row) for row in rows]

    def context(self, job_id: str) -> list[str]:
        return [item["content"] for item in self.list(job_id) if item["role"] == "user" and item["intent"] == "append_context"]

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        return {
            "message_id": row["message_id"],
            "job_id": row["job_id"],
            "role": row["role"],
            "intent": row["intent"],
            "content": row["content"],
            "metadata": _decode(row["metadata_json"], {}),
            "created_at": row["created_at"],
        }


class AgentChatQueue:
    STATUSES = {"queued", "running", "succeeded", "failed"}

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
                CREATE TABLE IF NOT EXISTS agent_chat_requests (
                    request_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    message_id TEXT NOT NULL UNIQUE REFERENCES job_messages(message_id),
                    status TEXT NOT NULL,
                    worker_id TEXT,
                    lease_expires_at DOUBLE PRECISION,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error_json {json_type},
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_chat_queue ON agent_chat_requests(status, created_at)"
            )

    def enqueue(self, job_id: str, message_id: str) -> Dict[str, Any]:
        self.job_store.require(job_id)
        request_id = f"chat_{uuid.uuid4().hex}"
        now = _utc_now()
        values = (request_id, job_id, message_id, "queued", now, now)
        with self.job_store._session() as connection:
            if self.postgres:
                connection.execute(
                    """INSERT INTO agent_chat_requests(request_id, job_id, message_id, status, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT(message_id) DO NOTHING""",
                    values,
                )
            else:
                connection.execute(
                    """INSERT OR IGNORE INTO agent_chat_requests(request_id, job_id, message_id, status, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    values,
                )
            row = connection.execute(
                f"SELECT * FROM agent_chat_requests WHERE message_id={self.placeholder}", (message_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to enqueue Agent conversation request")
        return self._row(row)

    def claim(self, worker_id: str, lease_seconds: float = 900.0) -> Optional[Dict[str, Any]]:
        owner = str(worker_id).strip() or "remote-planner"
        now_epoch = time.time()
        now = _utc_now()
        with self.job_store._session() as connection:
            if not self.postgres:
                connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                f"""UPDATE agent_chat_requests SET status='queued', worker_id=NULL, lease_expires_at=NULL, updated_at={self.placeholder}
                    WHERE status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at < {self.placeholder}""",
                (now, now_epoch),
            )
            suffix = " FOR UPDATE SKIP LOCKED" if self.postgres else ""
            row = connection.execute(
                "SELECT request_id FROM agent_chat_requests WHERE status='queued' ORDER BY created_at LIMIT 1" + suffix
            ).fetchone()
            if row is None:
                return None
            request_id = str(row["request_id"])
            updated = connection.execute(
                f"""UPDATE agent_chat_requests SET status='running', worker_id={self.placeholder},
                    lease_expires_at={self.placeholder}, attempts=attempts+1, updated_at={self.placeholder}
                    WHERE request_id={self.placeholder} AND status='queued'""",
                (owner, now_epoch + max(float(lease_seconds), 1.0), now, request_id),
            ).rowcount
            if updated != 1:
                return None
            claimed = connection.execute(
                f"SELECT * FROM agent_chat_requests WHERE request_id={self.placeholder}", (request_id,)
            ).fetchone()
        return self._row(claimed) if claimed is not None else None

    def complete(self, request_id: str) -> Dict[str, Any]:
        return self._finish(request_id, "succeeded", None)

    def fail(self, request_id: str, error: Mapping[str, Any]) -> Dict[str, Any]:
        return self._finish(request_id, "failed", error)

    def require(self, request_id: str) -> Dict[str, Any]:
        with self.job_store._session() as connection:
            row = connection.execute(
                f"SELECT * FROM agent_chat_requests WHERE request_id={self.placeholder}", (request_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown Agent conversation request {request_id!r}")
        return self._row(row)

    def pending(self, job_id: str) -> list[Dict[str, Any]]:
        self.job_store.require(job_id)
        with self.job_store._session() as connection:
            rows = connection.execute(
                f"""SELECT * FROM agent_chat_requests WHERE job_id={self.placeholder}
                    AND status IN ('queued', 'running') ORDER BY created_at""",
                (job_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def _finish(self, request_id: str, status: str, error: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        if status not in {"succeeded", "failed"}:
            raise ValueError("Unsupported terminal Agent conversation status")
        with self.job_store._session() as connection:
            updated = connection.execute(
                f"""UPDATE agent_chat_requests SET status={self.placeholder}, worker_id=NULL,
                    lease_expires_at=NULL, error_json={self.placeholder}, updated_at={self.placeholder}
                    WHERE request_id={self.placeholder} AND status='running'""",
                (status, _json(dict(error)) if error else None, _utc_now(), request_id),
            ).rowcount
            if updated != 1:
                current = connection.execute(
                    f"SELECT * FROM agent_chat_requests WHERE request_id={self.placeholder}", (request_id,)
                ).fetchone()
                if current is None:
                    raise KeyError(f"Unknown Agent conversation request {request_id!r}")
                if current["status"] != status:
                    raise RuntimeError(f"Agent conversation request is {current['status']!r}, not running")
                return self._row(current)
            row = connection.execute(
                f"SELECT * FROM agent_chat_requests WHERE request_id={self.placeholder}", (request_id,)
            ).fetchone()
        return self._row(row)

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        return {
            "request_id": row["request_id"],
            "job_id": row["job_id"],
            "message_id": row["message_id"],
            "status": row["status"],
            "worker_id": row["worker_id"],
            "lease_expires_at": row["lease_expires_at"],
            "attempts": int(row["attempts"]),
            "error": _decode(row["error_json"], None),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def job_status_answer(job: Any, steps: list[Any]) -> str:
    labels = {
        "queued_planning": "等待任务规划",
        "planning": "正在理解任务并生成执行路径",
        "queued_execution": "规划已完成，等待专家资源",
        "executing": "专家正在协同执行",
        "succeeded": "任务已完成，结果和证据已归档",
        "blocked_expert": "任务等待所需专家能力恢复",
        "failed": "任务执行未完成，可检查异常后重试",
        "cancelled": "任务已停止",
    }
    running = next((step for step in steps if step.status in {"running", "dispatched"}), None)
    completed = sum(1 for step in steps if step.status == "succeeded")
    parts = [labels.get(job.status, job.status)]
    if running is not None:
        progress = round(float(running.progress) * 100 if float(running.progress) <= 1 else float(running.progress))
        parts.append(f"当前由 {running.tool} 专家执行 {running.phase or '分析'}，进度 {progress}%")
    if steps:
        parts.append(f"已完成 {completed}/{len(steps)} 个专家步骤")
    artifacts = (job.result or {}).get("terminal_artifacts", {})
    if isinstance(artifacts, dict) and artifacts:
        parts.append(f"已归档 {len(artifacts)} 项结果产物")
    return "；".join(parts) + "。"
