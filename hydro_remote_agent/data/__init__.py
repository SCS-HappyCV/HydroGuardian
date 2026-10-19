"""VagueHydro dataset construction and auditing."""

from .vague_hydro import (
    CANONICAL_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    VagueHydroAuditError,
    audit_asset_paths,
    audit_dataset,
    build_canonical_records,
    build_source_manifest,
    load_jsonl,
    write_jsonl,
)

__all__ = [
    "CANONICAL_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "VagueHydroAuditError",
    "audit_asset_paths",
    "audit_dataset",
    "build_canonical_records",
    "build_source_manifest",
    "load_jsonl",
    "write_jsonl",
]
