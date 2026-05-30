from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException

from .bridge import HydroProgramBridge
from .config import load_settings
from .models import (
    BatchEvidenceCompileRequest,
    BatchEvidencePackResponse,
    EvidenceCompileRequest,
    EvidencePackResponse,
    ExecuteRequest,
    ExecuteResponse,
)
from .nacos import NacosRegistrar


def _resolve_execution_outputs(payload: EvidenceCompileRequest) -> dict:
    if payload.outputs:
        return payload.outputs
    raw = payload.execution_result or {}
    if not isinstance(raw, dict):
        return {}
    direct_outputs = raw.get("outputs")
    if isinstance(direct_outputs, dict):
        return direct_outputs
    nested = raw.get("execution_result")
    if isinstance(nested, dict):
        nested_outputs = nested.get("outputs")
        if isinstance(nested_outputs, dict):
            return nested_outputs
        return nested
    return raw


def create_app() -> FastAPI:
    settings = load_settings()
    bridge = HydroProgramBridge(settings)
    nacos = NacosRegistrar(settings)
    nacos_task: asyncio.Task | None = None

    app = FastAPI(title="hydro_program3d service", version="0.2.0")

    @app.on_event("startup")
    async def on_startup() -> None:
        nonlocal nacos_task
        if settings.nacos_enabled:
            nacos_task = asyncio.create_task(nacos.heartbeat_loop())

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        nonlocal nacos_task
        if nacos_task:
            nacos_task.cancel()
            nacos_task = None
        try:
            await nacos.deregister()
        except Exception as exc:
            print(f"[hydro-program3d] nacos deregister failed: {exc}")

    @app.get("/health")
    def health() -> dict:
        compiler_available = False
        compiler_error = None
        try:
            compiler_available = bridge.compiler_available
        except Exception as exc:
            compiler_error = str(exc)
        return {
            "ok": True,
            "service": "hydro_program3d",
            "service_root": str(settings.service_root),
            "algorithm_dir": str(settings.algorithm_dir),
            "data_dir": str(settings.data_dir),
            "checkpoint_dir": str(settings.checkpoint_dir),
            "compiler_available": compiler_available,
            "compiler_error": compiler_error or bridge.compiler_error,
            "nacos_enabled": settings.nacos_enabled,
            "nacos_service_name": settings.nacos_service_name,
            "nacos_registered": nacos.registered,
            "nacos_error": nacos.last_error,
        }

    @app.post("/execute", response_model=ExecuteResponse)
    def execute(payload: ExecuteRequest) -> ExecuteResponse:
        try:
            execution_result = bridge.execute(
                sample=payload.sample,
                program=payload.program,
                program_bundle=payload.program_bundle,
                checkpoint_name=payload.checkpoint_name,
                device=payload.device,
                model_overrides=payload.model_overrides,
            )
            return ExecuteResponse(
                ok=True,
                message="executed",
                service_root=str(settings.service_root),
                algorithm_dir=str(settings.algorithm_dir),
                checkpoint_name=execution_result.get("checkpoint_name"),
                checkpoint_path=execution_result.get("checkpoint_path"),
                execution_result=execution_result,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"execute failed: {exc}") from exc

    @app.post("/compile_evidence", response_model=EvidencePackResponse)
    def compile_evidence(payload: EvidenceCompileRequest) -> EvidencePackResponse:
        try:
            outputs = _resolve_execution_outputs(payload)
            if not outputs:
                raise ValueError("compile_evidence requires outputs or an /execute response body.")
            evidence_pack = bridge.compile_evidence(payload.sample, outputs, batch_index=payload.batch_index)
            return EvidencePackResponse(
                ok=True,
                message="compiled",
                service_root=str(settings.service_root),
                algorithm_dir=str(settings.algorithm_dir),
                evidence_pack=evidence_pack,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"compile failed: {exc}") from exc

    @app.post("/compile_evidence_batch", response_model=BatchEvidencePackResponse)
    def compile_batch(payload: BatchEvidenceCompileRequest) -> BatchEvidencePackResponse:
        try:
            result = bridge.compile_batch(payload.batch, payload.outputs)
            return BatchEvidencePackResponse(
                ok=True,
                message="compiled",
                service_root=str(settings.service_root),
                algorithm_dir=str(settings.algorithm_dir),
                evidence_packs=result["evidence_packs"],
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"compile-batch failed: {exc}") from exc

    return app
