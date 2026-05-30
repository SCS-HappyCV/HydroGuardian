from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvidenceCompileRequest(BaseModel):
    execution_result: Dict[str, Any] = Field(default_factory=dict)
    sample: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    batch_index: int = 0


class EvidencePackResponse(BaseModel):
    ok: bool
    message: str
    service_root: str
    algorithm_dir: str
    evidence_pack: Optional[Dict[str, Any]] = None


class ExecuteRequest(BaseModel):
    sample: Dict[str, Any] = Field(default_factory=dict)
    program: Optional[Dict[str, Any]] = None
    program_bundle: Optional[Dict[str, Any]] = None
    checkpoint_name: Optional[str] = None
    device: Optional[str] = None
    model_overrides: Dict[str, Any] = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    ok: bool
    message: str
    service_root: str
    algorithm_dir: str
    checkpoint_name: Optional[str] = None
    checkpoint_path: Optional[str] = None
    execution_result: Dict[str, Any] = Field(default_factory=dict)


class BatchEvidenceCompileRequest(BaseModel):
    batch: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)


class BatchEvidencePackResponse(BaseModel):
    ok: bool
    message: str
    service_root: str
    algorithm_dir: str
    evidence_packs: List[Dict[str, Any]] = Field(default_factory=list)
