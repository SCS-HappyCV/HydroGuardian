from __future__ import annotations

import hashlib
import mimetypes
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional


ARTIFACT_URI_PATTERN = re.compile(r"^artifact://([A-Za-z0-9_-]+)$")


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    bucket: str
    object_key: str
    media_type: str
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    metadata: dict[str, Any] = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata or {})
        return payload


class MinioAssetStore:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, *,
                 secure: bool = False, input_bucket: str = "hydro-input",
                 output_bucket: str = "hydro-output", public_endpoint: Optional[str] = None) -> None:
        try:
            from minio import Minio
        except ImportError as exc:
            raise RuntimeError("MinIO asset storage requires minio") from exc
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self.presign_client = Minio(
            public_endpoint or endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self.input_bucket = input_bucket
        self.output_bucket = output_bucket
        self.ensure_buckets()

    def ensure_buckets(self) -> None:
        for bucket in (self.input_bucket, self.output_bucket):
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)

    @staticmethod
    def new_artifact_id() -> str:
        return f"art_{uuid.uuid4().hex}"

    def presign_upload(self, filename: str, *, tenant_id: str = "default",
                       job_id: str = "uploads", media_type: Optional[str] = None) -> dict[str, Any]:
        artifact_id = self.new_artifact_id()
        safe_name = Path(filename).name
        object_key = f"{tenant_id}/{job_id}/input/{artifact_id}/{safe_name}"
        record = ArtifactRecord(
            artifact_id=artifact_id,
            bucket=self.input_bucket,
            object_key=object_key,
            media_type=media_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
            metadata={},
        )
        return {"artifact": record.to_dict(), "upload_url": self.presign_client.presigned_put_object(
            self.input_bucket, object_key
        )}

    def stat(self, record: ArtifactRecord) -> ArtifactRecord:
        value = self.client.stat_object(record.bucket, record.object_key)
        metadata = dict(record.metadata or {})
        metadata.update(dict(value.metadata or {}))
        return ArtifactRecord(
            artifact_id=record.artifact_id, bucket=record.bucket, object_key=record.object_key,
            media_type=record.media_type, size_bytes=value.size, sha256=record.sha256, metadata=metadata,
        )

    def presign_download(self, record: ArtifactRecord) -> str:
        return self.presign_client.presigned_get_object(record.bucket, record.object_key)

    def download(self, record: ArtifactRecord, target: str | Path) -> Path:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.client.fget_object(record.bucket, record.object_key, str(path))
        if record.sha256 and file_sha256(path) != record.sha256:
            path.unlink(missing_ok=True)
            raise ValueError(f"SHA-256 mismatch for artifact {record.artifact_id}")
        return path

    def upload(self, source: str | Path, *, artifact_id: Optional[str] = None,
               job_id: str = "jobs", step_id: str = "step", name: Optional[str] = None,
               metadata: Optional[Mapping[str, Any]] = None) -> ArtifactRecord:
        path = Path(source)
        resolved_id = artifact_id or self.new_artifact_id()
        filename = Path(name).name if name else path.name
        object_key = f"default/{job_id}/{step_id}/{resolved_id}/{filename}"
        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self.client.fput_object(self.output_bucket, object_key, str(path), content_type=media_type)
        return ArtifactRecord(
            artifact_id=resolved_id, bucket=self.output_bucket, object_key=object_key,
            media_type=media_type, size_bytes=path.stat().st_size, sha256=file_sha256(path),
            metadata=dict(metadata or {}),
        )


class ArtifactCatalog:
    """Catalog persisted in PostgreSQL; in-memory fallback is available for tests."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.database_url = database_url
        self._records: dict[str, ArtifactRecord] = {}
        if database_url:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError("PostgreSQL artifact catalog requires psycopg") from exc
            self._psycopg = psycopg
            self._row_factory = dict_row
            self.initialize()

    def initialize(self) -> None:
        if not self.database_url:
            return
        with self._psycopg.connect(self.database_url, row_factory=self._row_factory) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY, bucket TEXT NOT NULL, object_key TEXT NOT NULL,
                    media_type TEXT NOT NULL, size_bytes BIGINT, sha256 TEXT,
                    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(bucket, object_key)
                )
            """)

    def put(self, record: ArtifactRecord) -> ArtifactRecord:
        if not self.database_url:
            self._records[record.artifact_id] = record
            return record
        import json
        with self._psycopg.connect(self.database_url, row_factory=self._row_factory) as connection:
            connection.execute(
                """INSERT INTO artifacts(artifact_id, bucket, object_key, media_type, size_bytes, sha256, metadata_json)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (artifact_id) DO UPDATE SET size_bytes=EXCLUDED.size_bytes,
                   sha256=EXCLUDED.sha256, metadata_json=EXCLUDED.metadata_json""",
                (record.artifact_id, record.bucket, record.object_key, record.media_type,
                 record.size_bytes, record.sha256, json.dumps(record.metadata or {})),
            )
        return record

    def get(self, artifact_id: str) -> Optional[ArtifactRecord]:
        if not self.database_url:
            return self._records.get(artifact_id)
        with self._psycopg.connect(self.database_url, row_factory=self._row_factory) as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE artifact_id=%s", (artifact_id,)).fetchone()
        if row is None:
            return None
        metadata = row["metadata_json"]
        if isinstance(metadata, str):
            import json
            metadata = json.loads(metadata)
        return ArtifactRecord(
            artifact_id=row["artifact_id"], bucket=row["bucket"], object_key=row["object_key"],
            media_type=row["media_type"], size_bytes=row["size_bytes"], sha256=row["sha256"],
            metadata=dict(metadata or {}),
        )


def artifact_id_from_uri(value: str) -> Optional[str]:
    match = ARTIFACT_URI_PATTERN.fullmatch(value)
    return match.group(1) if match else None


def resolve_artifact_references(value: Any, catalog: ArtifactCatalog) -> Any:
    if isinstance(value, str):
        artifact_id = artifact_id_from_uri(value)
        if artifact_id is None:
            return value
        record = catalog.get(artifact_id)
        if record is None:
            raise KeyError(f"Unknown artifact {artifact_id!r}")
        return {"$artifact": record.to_dict()}
    if isinstance(value, dict):
        return {key: resolve_artifact_references(child, catalog) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve_artifact_references(child, catalog) for child in value]
    return value


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
