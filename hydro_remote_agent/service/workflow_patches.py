from __future__ import annotations

import json
import re
import uuid
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


PATCH_COMMAND_PATTERN = re.compile(r"添加|增加|追加|插入|再做|再执行|再调用|补充.*专家")
TOOL_ALIASES = (
    ("point_semantic_segmentation", re.compile(r"点云语义(?:分割|分析)|GUFNet", re.I)),
    ("image_change_detection", re.compile(r"变化检测|变化检查|前后时相", re.I)),
    ("language_guided_point_segmentation", re.compile(r"语言引导.*点云|目标点云定位|HydroProgram3D", re.I)),
)


def infer_workflow_patch(content: str, submission: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    text = str(content).strip()
    if not PATCH_COMMAND_PATTERN.search(text):
        return None
    tool = next((name for name, pattern in TOOL_ALIASES if pattern.search(text)), None)
    if tool is None:
        return None
    assets = submission.get("assets") if isinstance(submission.get("assets"), dict) else {}
    if tool == "point_semantic_segmentation":
        point_cloud = assets.get("point_cloud_path")
        if not isinstance(point_cloud, str) or not point_cloud:
            raise ValueError("追加点云语义分割需要当前任务包含点云数据")
        arguments = {"point_cloud_path": point_cloud, "return_probabilities": True}
    elif tool == "image_change_detection":
        before = assets.get("before_image_path")
        after = assets.get("after_image_path")
        if not isinstance(before, str) or not isinstance(after, str) or not before or not after:
            raise ValueError("追加变化检测需要当前任务包含前后时相影像")
        arguments = {
            "before_image_path": before, "after_image_path": after,
            "change_threshold": 0.0005, "minimum_region_pixels": 20,
            "return_probability_map": True,
        }
    else:
        image = assets.get("image_path") or assets.get("after_image_path")
        point_cloud = assets.get("point_cloud_path")
        if not isinstance(image, str) or not isinstance(point_cloud, str) or not image or not point_cloud:
            raise ValueError("追加语言引导点云定位需要当前任务同时包含影像和点云数据")
        arguments = {
            "image_path": image, "point_cloud_path": point_cloud,
            "query": text, "return_probabilities": True,
        }
    return {"tool": tool, "arguments": arguments, "verification": "auto"}


class WorkflowPatchStore:
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
                CREATE TABLE IF NOT EXISTS workflow_patches (
                    patch_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    source_message_id TEXT NOT NULL UNIQUE REFERENCES job_messages(message_id),
                    step_id TEXT NOT NULL UNIQUE,
                    tool TEXT NOT NULL,
                    arguments_json {json_type} NOT NULL,
                    verification TEXT NOT NULL,
                    status TEXT NOT NULL,
                    worker_id TEXT,
                    error_json {json_type},
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_patches_job ON workflow_patches(job_id, status, created_at)"
            )

    def enqueue(
        self,
        job_id: str,
        source_message_id: str,
        tool: str,
        arguments: Mapping[str, Any],
        verification: str = "auto",
    ) -> Dict[str, Any]:
        current = self.job_store.require(job_id)
        if current.status not in {"queued_execution", "executing", "succeeded"}:
            raise ValueError(f"当前任务状态 {current.status} 不允许追加专家步骤")
        patch_id = f"patch_{uuid.uuid4().hex}"
        step_id = f"runtime_{tool}_{uuid.uuid4().hex[:6]}_invoke"
        now = _utc_now()
        values = (
            patch_id, job_id, source_message_id, step_id, tool,
            _json(dict(arguments)), verification, "queued", now, now,
        )
        with self.job_store._session() as connection:
            if self.postgres:
                connection.execute(
                    """INSERT INTO workflow_patches(
                           patch_id, job_id, source_message_id, step_id, tool, arguments_json,
                           verification, status, created_at, updated_at
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT(source_message_id) DO NOTHING""",
                    values,
                )
            else:
                connection.execute(
                    """INSERT OR IGNORE INTO workflow_patches(
                           patch_id, job_id, source_message_id, step_id, tool, arguments_json,
                           verification, status, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
            inserted = connection.execute(
                f"SELECT patch_id FROM workflow_patches WHERE patch_id={self.placeholder}", (patch_id,),
            ).fetchone() is not None
            row = connection.execute(
                f"SELECT * FROM workflow_patches WHERE source_message_id={self.placeholder}",
                (source_message_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to enqueue Workflow Patch")
        patch = self._row(row)
        if inserted:
            self.job_store.upsert_step(
                patch["step_id"], job_id, patch["tool"], status="pending",
                progress=0.0, phase="workflow_patch_queued", arguments=patch["arguments"],
            )
            self._activate_job(job_id)
        return patch

    def _activate_job(self, job_id: str) -> None:
        current = self.job_store.require(job_id)
        now = _utc_now()
        with self.job_store._session() as connection:
            if current.status == "succeeded":
                connection.execute(
                    f"""UPDATE jobs SET status='queued_execution', lease_owner=NULL, lease_expires_at=NULL,
                        updated_at={self.placeholder}, version=version+1 WHERE job_id={self.placeholder} AND status='succeeded'""",
                    (now, job_id),
                )
            else:
                connection.execute(
                    f"UPDATE jobs SET updated_at={self.placeholder}, version=version+1 WHERE job_id={self.placeholder}",
                    (now, job_id),
                )

    def ensure_queued_execution(self, job_id: str) -> None:
        if not self.has_queued(job_id):
            return
        current = self.job_store.require(job_id)
        if current.status != "succeeded":
            return
        self._activate_job(job_id)

    def claim(self, job_id: str, worker_id: str) -> Optional[Dict[str, Any]]:
        now = _utc_now()
        with self.job_store._session() as connection:
            suffix = " FOR UPDATE SKIP LOCKED" if self.postgres else ""
            row = connection.execute(
                f"""SELECT patch_id FROM workflow_patches
                    WHERE job_id={self.placeholder} AND status='queued'
                    ORDER BY created_at LIMIT 1{suffix}""",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            patch_id = str(row["patch_id"])
            updated = connection.execute(
                f"""UPDATE workflow_patches SET status='running', worker_id={self.placeholder},
                    updated_at={self.placeholder} WHERE patch_id={self.placeholder} AND status='queued'""",
                (worker_id, now, patch_id),
            ).rowcount
            if updated != 1:
                return None
            claimed = connection.execute(
                f"SELECT * FROM workflow_patches WHERE patch_id={self.placeholder}", (patch_id,),
            ).fetchone()
        patch = self._row(claimed)
        self.job_store.upsert_step(
            patch["step_id"], job_id, patch["tool"], status="dispatched",
            worker_id=worker_id, progress=0.0, phase="workflow_patch_running",
            arguments=patch["arguments"],
        )
        return patch

    def has_queued(self, job_id: str) -> bool:
        with self.job_store._session() as connection:
            row = connection.execute(
                f"""SELECT patch_id FROM workflow_patches
                    WHERE job_id={self.placeholder} AND status='queued' LIMIT 1""",
                (job_id,),
            ).fetchone()
        return row is not None

    def complete(self, patch_id: str, result: Mapping[str, Any]) -> Dict[str, Any]:
        patch = self.require(patch_id)
        with self.job_store._session() as connection:
            updated = connection.execute(
                f"""UPDATE workflow_patches SET status='succeeded', worker_id=NULL, error_json=NULL,
                    updated_at={self.placeholder} WHERE patch_id={self.placeholder} AND status='running'""",
                (_utc_now(), patch_id),
            ).rowcount
            if updated != 1:
                raise RuntimeError("Workflow Patch is not running")
        current_step = self.job_store.step(patch["step_id"])
        if current_step.status != "succeeded":
            workflow = result.get("workflow_result") if isinstance(result.get("workflow_result"), dict) else {}
            steps = workflow.get("steps") if isinstance(workflow.get("steps"), list) else []
            expert_result = steps[0].get("result") if steps and isinstance(steps[0], dict) else None
            self.job_store.upsert_step(
                patch["step_id"], patch["job_id"], patch["tool"], status="succeeded",
                progress=1.0, phase="completed", arguments=patch["arguments"],
                result=expert_result if isinstance(expert_result, dict) else dict(result),
            )
        return self.require(patch_id)

    def fail(self, patch_id: str, error: Mapping[str, Any]) -> Dict[str, Any]:
        patch = self.require(patch_id)
        recorded_step = self.job_store.step(patch["step_id"])
        resolved_error = (
            dict(recorded_step.error)
            if recorded_step.error
            else dict(error)
        )
        with self.job_store._session() as connection:
            connection.execute(
                f"""UPDATE workflow_patches SET status='failed', worker_id=NULL,
                    error_json={self.placeholder}, updated_at={self.placeholder}
                    WHERE patch_id={self.placeholder} AND status='running'""",
                (_json(resolved_error), _utc_now(), patch_id),
            )
        self.job_store.upsert_step(
            patch["step_id"], patch["job_id"], patch["tool"], status="failed",
            progress=0.0, phase="workflow_patch_failed", arguments=patch["arguments"], error=resolved_error,
        )
        return self.require(patch_id)

    def require(self, patch_id: str) -> Dict[str, Any]:
        with self.job_store._session() as connection:
            row = connection.execute(
                f"SELECT * FROM workflow_patches WHERE patch_id={self.placeholder}", (patch_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown Workflow Patch {patch_id!r}")
        return self._row(row)

    @staticmethod
    def _row(row: Any) -> Dict[str, Any]:
        return {
            "patch_id": row["patch_id"],
            "job_id": row["job_id"],
            "source_message_id": row["source_message_id"],
            "step_id": row["step_id"],
            "tool": row["tool"],
            "arguments": _decode(row["arguments_json"], {}),
            "verification": row["verification"],
            "status": row["status"],
            "worker_id": row["worker_id"],
            "error": _decode(row["error_json"], None),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
