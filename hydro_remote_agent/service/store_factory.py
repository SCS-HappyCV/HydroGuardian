from __future__ import annotations

from pathlib import Path
from typing import Any

from .store import JobStore


def create_job_store(database: str | Path) -> Any:
    value = str(database)
    if value.startswith(("postgresql://", "postgresql+psycopg://")):
        from .postgres_store import PostgresJobStore

        return PostgresJobStore(value.replace("postgresql+psycopg://", "postgresql://", 1))
    return JobStore(value)
