from __future__ import annotations

import json
import hashlib
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


WORKORDER_STATUSES = {"todo", "doing", "review", "closed"}


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


def _location_snapshot(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    try:
        longitude = float(value["longitude"])
        latitude = float(value["latitude"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        return None
    location: Dict[str, Any] = {"longitude": longitude, "latitude": latitude}
    for source, target in (("projected_x", "projected_x"), ("projected_y", "projected_y"), ("epsg", "epsg")):
        raw = value.get(source)
        if raw is None:
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            location[target] = int(number) if source == "epsg" else number
    if isinstance(value.get("crs_name"), str):
        location["crs_name"] = value["crs_name"]
    bbox = value.get("geographic_bbox")
    if isinstance(bbox, Mapping):
        try:
            normalized_bbox = {key: float(bbox[key]) for key in ("west", "south", "east", "north")}
        except (KeyError, TypeError, ValueError):
            normalized_bbox = {}
        if normalized_bbox and all(math.isfinite(item) for item in normalized_bbox.values()):
            location["geographic_bbox"] = normalized_bbox
    return location


class WorkorderStore:
    def __init__(self, job_store: Any) -> None:
        self.job_store = job_store
        self.postgres = job_store.__class__.__name__ == "PostgresJobStore"
        self.placeholder = "%s" if self.postgres else "?"
        self.initialize()

    def initialize(self) -> None:
        json_type = "JSONB" if self.postgres else "TEXT"
        event_id = "BIGSERIAL PRIMARY KEY" if self.postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        with self.job_store._session() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS workorders (
                    workorder_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    candidate_id TEXT NOT NULL,
                    region_id TEXT NOT NULL DEFAULT '',
                    task_id TEXT,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    risk_type TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    score DOUBLE PRECISION NOT NULL DEFAULT 0,
                    rule_id TEXT,
                    recommendation TEXT,
                    priority TEXT,
                    assignee_user_id TEXT,
                    reviewer_user_id TEXT,
                    due_at TEXT,
                    risk_snapshot_json {json_type} NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(job_id, candidate_id, region_id)
                )
                """
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS workorder_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    workorder_id TEXT NOT NULL REFERENCES workorders(workorder_id),
                    evidence_type TEXT NOT NULL,
                    artifact_id TEXT,
                    title TEXT NOT NULL,
                    content TEXT,
                    media_type TEXT,
                    metadata_json {json_type} NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS workorder_reviews (
                    review_id TEXT PRIMARY KEY,
                    workorder_id TEXT NOT NULL REFERENCES workorders(workorder_id),
                    reviewer_user_id TEXT,
                    decision TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    evidence_note TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS workorder_timeline (
                    event_id {event_id},
                    workorder_id TEXT NOT NULL REFERENCES workorders(workorder_id),
                    actor_user_id TEXT,
                    action TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT,
                    note TEXT,
                    payload_json {json_type} NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workorder_submissions (
                    submission_id TEXT PRIMARY KEY,
                    workorder_id TEXT NOT NULL REFERENCES workorders(workorder_id),
                    payload_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_workorders_status_updated ON workorders(status, updated_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_workorder_timeline_order ON workorder_timeline(workorder_id, event_id)"
            )

    def create_from_candidate(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        job_id = self._required_text(payload, "job_id")
        candidate_id = self._required_text(payload, "candidate_id")
        region_id = str(payload.get("region_id") or "").strip()
        job = self.job_store.require(job_id)
        candidates = (job.result or {}).get("risk_candidates", [])
        candidate = next(
            (item for item in candidates if isinstance(item, dict) and item.get("candidate_id") == candidate_id),
            None,
        )
        if candidate is None:
            raise ValueError("Risk candidate does not belong to the specified job")
        existing = self._find_unique(job_id, candidate_id, region_id)
        if existing is not None:
            return self.require(existing)

        workorder_id = f"wo_{uuid.uuid4().hex}"
        now = _utc_now()
        risk_snapshot = dict(candidate)
        if region_id:
            risk_snapshot["selected_region_id"] = region_id
        location = _location_snapshot(payload.get("location"))
        if location:
            risk_snapshot["location"] = location
        values = (
            workorder_id, job_id, candidate_id, region_id, payload.get("task_id"), "todo",
            str(candidate.get("title") or "待核查风险"), str(candidate.get("summary") or ""),
            str(candidate.get("risk_type") or "other"), str(candidate.get("risk_level") or "medium"),
            float(candidate.get("score") or 0), candidate.get("rule_id"), candidate.get("recommendation"),
            payload.get("priority") or candidate.get("risk_level"), payload.get("assignee_user_id"),
            payload.get("reviewer_user_id"), payload.get("due_at"), _json(risk_snapshot), now, now,
        )
        marks = ", ".join([self.placeholder] * len(values))
        with self.job_store._session() as connection:
            connection.execute(
                f"""INSERT INTO workorders(
                    workorder_id, job_id, candidate_id, region_id, task_id, status, title, summary,
                    risk_type, risk_level, score, rule_id, recommendation, priority, assignee_user_id,
                    reviewer_user_id, due_at, risk_snapshot_json, created_at, updated_at
                ) VALUES ({marks})""",
                values,
            )
            self._timeline(connection, workorder_id, payload.get("actor_user_id"), "created", None, "todo", "风险研判已生成核查工单", {})
            for ref in candidate.get("evidence_refs", []):
                if isinstance(ref, str):
                    artifact_id = ref.removeprefix("artifact://") if ref.startswith("artifact://") else None
                    self._insert_evidence(connection, workorder_id, {
                        "evidence_type": "source", "artifact_id": artifact_id,
                        "title": "Agent 研判证据", "content": ref, "metadata": {"artifact_uri": ref},
                    })
                    continue
                if not isinstance(ref, dict):
                    continue
                self._insert_evidence(connection, workorder_id, {
                    "evidence_type": "source",
                    "artifact_id": ref.get("artifact_id"),
                    "title": ref.get("title") or ref.get("role") or "Agent 研判证据",
                    "content": ref.get("summary") or ref.get("artifact_uri") or "",
                    "media_type": ref.get("media_type"),
                    "metadata": ref,
                })
            source_titles = {
                "before_image_path": "巡查前时相影像",
                "after_image_path": "风险发现时相影像",
                "image_path": "任务现场影像",
                "point_cloud_path": "现场三维点云",
            }
            candidate_artifacts = {
                str(ref).removeprefix("artifact://")
                for ref in candidate.get("evidence_refs", [])
                if isinstance(ref, str) and str(ref).startswith("artifact://")
            }
            submission_assets = job.submission.get("assets", {}) if isinstance(job.submission, Mapping) else {}
            for role, uri in submission_assets.items():
                if role not in source_titles or not isinstance(uri, str) or not uri.startswith("artifact://"):
                    continue
                artifact_id = uri.removeprefix("artifact://")
                if artifact_id in candidate_artifacts:
                    continue
                self._insert_evidence(connection, workorder_id, {
                    "evidence_type": "source",
                    "artifact_id": artifact_id,
                    "title": source_titles[role],
                    "content": "任务输入原始空间证据",
                    "metadata": {"artifact_uri": uri, "role": role},
                })
        return self.aggregate(workorder_id)

    def list(self, *, status: Optional[str] = None, task_id: Optional[str] = None, job_id: Optional[str] = None, limit: int = 100) -> list[Dict[str, Any]]:
        if status and status not in WORKORDER_STATUSES:
            raise ValueError("Unsupported workorder status")
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (("status", status), ("task_id", task_id), ("job_id", job_id)):
            if value:
                clauses.append(f"{column}={self.placeholder}")
                params.append(value)
        query = "SELECT workorder_id FROM workorders"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += f" ORDER BY updated_at DESC LIMIT {self.placeholder}"
        params.append(max(1, min(int(limit), 1000)))
        with self.job_store._session() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self.aggregate(str(row["workorder_id"])) for row in rows]

    def require(self, workorder_id: str) -> Dict[str, Any]:
        with self.job_store._session() as connection:
            row = connection.execute(
                f"SELECT * FROM workorders WHERE workorder_id={self.placeholder}", (workorder_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown workorder {workorder_id!r}")
        return self._workorder(row)

    def aggregate(self, workorder_id: str) -> Dict[str, Any]:
        order = self.require(workorder_id)
        with self.job_store._session() as connection:
            evidence = connection.execute(
                f"SELECT * FROM workorder_evidence WHERE workorder_id={self.placeholder} ORDER BY created_at", (workorder_id,)
            ).fetchall()
            reviews = connection.execute(
                f"SELECT * FROM workorder_reviews WHERE workorder_id={self.placeholder} ORDER BY created_at", (workorder_id,)
            ).fetchall()
            timeline = connection.execute(
                f"SELECT * FROM workorder_timeline WHERE workorder_id={self.placeholder} ORDER BY event_id", (workorder_id,)
            ).fetchall()
        order["evidence"] = [self._evidence(row) for row in evidence]
        order["reviews"] = [self._review(row) for row in reviews]
        order["timeline"] = [self._event(row) for row in timeline]
        return order

    def assign(self, workorder_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        assignee = self._required_text(payload, "assignee_user_id")
        reviewer = payload.get("reviewer_user_id")
        due_at = payload.get("due_at")
        current = self.require(workorder_id)
        if current["status"] == "closed":
            raise ValueError("Closed workorder cannot be reassigned")
        with self.job_store._session() as connection:
            connection.execute(
                f"UPDATE workorders SET assignee_user_id={self.placeholder}, reviewer_user_id=COALESCE({self.placeholder}, reviewer_user_id), due_at=COALESCE({self.placeholder}, due_at), updated_at={self.placeholder}, version=version+1 WHERE workorder_id={self.placeholder}",
                (assignee, reviewer, due_at, _utc_now(), workorder_id),
            )
            self._timeline(connection, workorder_id, payload.get("actor_user_id"), "assigned", current["status"], current["status"], str(payload.get("note") or "工单已指派"), {"assignee_user_id": assignee})
        return self.aggregate(workorder_id)

    def start(self, workorder_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._transition(workorder_id, {"todo"}, "doing", "processing", payload, "现场核查已开始")

    def feedback(self, workorder_id: str, payload: Mapping[str, Any], catalog: Any = None) -> Dict[str, Any]:
        submission_id = str(payload.get("client_submission_id") or "").strip()
        if submission_id:
            existing_workorder = self._submission_workorder(submission_id)
            if existing_workorder:
                if existing_workorder != workorder_id:
                    raise ValueError("client_submission_id already belongs to another workorder")
                return self.aggregate(workorder_id)
        current = self.require(workorder_id)
        expected_version = payload.get("expected_version")
        if expected_version is not None:
            try:
                normalized_version = int(expected_version)
            except (TypeError, ValueError) as exc:
                raise ValueError("expected_version must be an integer") from exc
            if normalized_version != current["version"]:
                raise ValueError(
                    f"Workorder version conflict: expected {normalized_version}, current {current['version']}"
                )
        if current["status"] not in {"doing", "todo"}:
            raise ValueError("Only pending or processing workorders can submit feedback")
        note = self._required_text(payload, "note")
        attachments = payload.get("evidence", [])
        if not isinstance(attachments, list):
            raise ValueError("evidence must be a list")
        with self.job_store._session() as connection:
            self._insert_evidence(connection, workorder_id, {"evidence_type": "note", "title": "现场核查说明", "content": note})
            for item in attachments:
                if not isinstance(item, dict):
                    raise ValueError("Each evidence item must be an object")
                artifact_id = self._required_text(item, "artifact_id")
                record = catalog.get(artifact_id) if catalog is not None else None
                if record is None:
                    raise ValueError(f"Unknown artifact {artifact_id!r}")
                self._insert_evidence(connection, workorder_id, {
                    "evidence_type": "after", "artifact_id": artifact_id,
                    "title": item.get("title") or "现场反馈附件", "content": item.get("content") or "",
                    "media_type": record.media_type, "metadata": dict(item.get("metadata") or {}),
                })
            now = _utc_now()
            connection.execute(
                f"UPDATE workorders SET status='review', updated_at={self.placeholder}, version=version+1 WHERE workorder_id={self.placeholder}",
                (now, workorder_id),
            )
            self._timeline(connection, workorder_id, payload.get("actor_user_id"), "review_requested", current["status"], "review", "现场反馈已提交，等待人工复核", {"evidence_count": len(attachments)})
            if submission_id:
                digest = hashlib.sha256(_json(dict(payload)).encode("utf-8")).hexdigest()
                connection.execute(
                    f"INSERT INTO workorder_submissions(submission_id, workorder_id, payload_digest, created_at) VALUES ({', '.join([self.placeholder] * 4)})",
                    (submission_id, workorder_id, digest, now),
                )
        return self.aggregate(workorder_id)

    def review(self, workorder_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        current = self.require(workorder_id)
        if current["status"] != "review":
            raise ValueError("Only workorders awaiting review can be reviewed")
        decision = self._required_text(payload, "decision")
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        comment = self._required_text(payload, "comment")
        reviewer = payload.get("reviewer_user_id") or current.get("reviewer_user_id")
        new_status = "closed" if decision == "approved" else "doing"
        now = _utc_now()
        review_id = f"review_{uuid.uuid4().hex}"
        with self.job_store._session() as connection:
            connection.execute(
                f"INSERT INTO workorder_reviews(review_id, workorder_id, reviewer_user_id, decision, comment, evidence_note, created_at) VALUES ({', '.join([self.placeholder] * 7)})",
                (review_id, workorder_id, reviewer, decision, comment, payload.get("evidence_note"), now),
            )
            connection.execute(
                f"UPDATE workorders SET status={self.placeholder}, reviewer_user_id=COALESCE({self.placeholder}, reviewer_user_id), updated_at={self.placeholder}, version=version+1 WHERE workorder_id={self.placeholder}",
                (new_status, reviewer, now, workorder_id),
            )
            action = "closed" if decision == "approved" else "reviewed"
            self._timeline(connection, workorder_id, reviewer, action, "review", new_status, comment, {"decision": decision, "review_id": review_id})
        return self.aggregate(workorder_id)

    def _transition(self, workorder_id: str, allowed: set[str], new_status: str, action: str, payload: Mapping[str, Any], note: str) -> Dict[str, Any]:
        current = self.require(workorder_id)
        if current["status"] not in allowed:
            raise ValueError(f"Workorder cannot transition from {current['status']} to {new_status}")
        with self.job_store._session() as connection:
            connection.execute(
                f"UPDATE workorders SET status={self.placeholder}, updated_at={self.placeholder}, version=version+1 WHERE workorder_id={self.placeholder}",
                (new_status, _utc_now(), workorder_id),
            )
            self._timeline(connection, workorder_id, payload.get("actor_user_id"), action, current["status"], new_status, str(payload.get("note") or note), {})
        return self.aggregate(workorder_id)

    def _find_unique(self, job_id: str, candidate_id: str, region_id: str) -> Optional[str]:
        with self.job_store._session() as connection:
            row = connection.execute(
                f"SELECT workorder_id FROM workorders WHERE job_id={self.placeholder} AND candidate_id={self.placeholder} AND region_id={self.placeholder}",
                (job_id, candidate_id, region_id),
            ).fetchone()
        return str(row["workorder_id"]) if row else None

    def _submission_workorder(self, submission_id: str) -> Optional[str]:
        with self.job_store._session() as connection:
            row = connection.execute(
                f"SELECT workorder_id FROM workorder_submissions WHERE submission_id={self.placeholder}",
                (submission_id,),
            ).fetchone()
        return str(row["workorder_id"]) if row else None

    def _insert_evidence(self, connection: Any, workorder_id: str, item: Mapping[str, Any]) -> None:
        evidence_id = f"evidence_{uuid.uuid4().hex}"
        values = (evidence_id, workorder_id, item.get("evidence_type") or "note", item.get("artifact_id"), item.get("title") or "证据", item.get("content"), item.get("media_type"), _json(dict(item.get("metadata") or {})), _utc_now())
        connection.execute(
            f"INSERT INTO workorder_evidence(evidence_id, workorder_id, evidence_type, artifact_id, title, content, media_type, metadata_json, created_at) VALUES ({', '.join([self.placeholder] * 9)})",
            values,
        )

    def _timeline(self, connection: Any, workorder_id: str, actor: Any, action: str, old: Optional[str], new: Optional[str], note: str, payload: Mapping[str, Any]) -> None:
        connection.execute(
            f"INSERT INTO workorder_timeline(workorder_id, actor_user_id, action, from_status, to_status, note, payload_json, created_at) VALUES ({', '.join([self.placeholder] * 8)})",
            (workorder_id, actor, action, old, new, note, _json(dict(payload)), _utc_now()),
        )

    @staticmethod
    def _required_text(payload: Mapping[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} is required")
        return value.strip()

    @staticmethod
    def _workorder(row: Any) -> Dict[str, Any]:
        return {
            "workorder_id": row["workorder_id"], "job_id": row["job_id"], "candidate_id": row["candidate_id"],
            "region_id": row["region_id"], "task_id": row["task_id"], "status": row["status"], "title": row["title"],
            "summary": row["summary"], "risk_type": row["risk_type"], "risk_level": row["risk_level"],
            "score": float(row["score"]), "rule_id": row["rule_id"], "recommendation": row["recommendation"],
            "priority": row["priority"], "assignee_user_id": row["assignee_user_id"], "reviewer_user_id": row["reviewer_user_id"],
            "due_at": row["due_at"], "risk_snapshot": _decode(row["risk_snapshot_json"], {}),
            "created_at": row["created_at"], "updated_at": row["updated_at"], "version": int(row["version"]),
        }

    @staticmethod
    def _evidence(row: Any) -> Dict[str, Any]:
        return {"evidence_id": row["evidence_id"], "evidence_type": row["evidence_type"], "artifact_id": row["artifact_id"], "title": row["title"], "content": row["content"], "media_type": row["media_type"], "metadata": _decode(row["metadata_json"], {}), "created_at": row["created_at"]}

    @staticmethod
    def _review(row: Any) -> Dict[str, Any]:
        return {"review_id": row["review_id"], "reviewer_user_id": row["reviewer_user_id"], "decision": row["decision"], "comment": row["comment"], "evidence_note": row["evidence_note"], "created_at": row["created_at"]}

    @staticmethod
    def _event(row: Any) -> Dict[str, Any]:
        return {"event_id": int(row["event_id"]), "actor_user_id": row["actor_user_id"], "action": row["action"], "from_status": row["from_status"], "to_status": row["to_status"], "note": row["note"], "payload": _decode(row["payload_json"], {}), "created_at": row["created_at"]}
