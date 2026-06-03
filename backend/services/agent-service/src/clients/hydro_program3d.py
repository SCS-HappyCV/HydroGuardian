# hydro-program3d 服务客户端。
# 本文件负责服务发现、健康检查、/execute、/compile_evidence 和失败降级证据包。

from __future__ import annotations

import time
from typing import Any, Dict

import httpx

from config import (
    HYDRO_PROGRAM3D_CHECKPOINT_NAME,
    HYDRO_PROGRAM3D_DEVICE,
    HYDRO_PROGRAM3D_SERVICE_NAME,
    HYDRO_PROGRAM3D_TIMEOUT_SECONDS,
    HYDRO_PROGRAM3D_URL,
    default_model_overrides,
)
from clients.hydro_program3d_support import (
    HydroProgram3DError,
    build_compile_request,
    classify_httpx_error,
    http_status_error,
    summarize_execute_request,
    validate_evidence_pack,
)
from discovery import resolve_http_base_url
from state import AgentState, append_error, append_trace, failure_evidence_pack


# hydro-program3d 主执行链路最多尝试两次：首次失败后只对可重试错误再试一次。
MAX_EXECUTE_ATTEMPTS = 2


# 计算当前时间点，用于 HTTP 阶段耗时统计。
def _now() -> float:
    return time.perf_counter()


# 将开始时间转换成毫秒耗时。
def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


# 构造 hydro-program3d /execute 请求体。
def build_execute_request(state: AgentState) -> Dict[str, Any]:
    # 请求体尽量贴近 hydro-program3d 的公开契约，
    # 这样服务 README 仍然能直接拿来当联调参考。
    body = {
        "checkpoint_name": HYDRO_PROGRAM3D_CHECKPOINT_NAME,
        "device": HYDRO_PROGRAM3D_DEVICE,
        "model_overrides": default_model_overrides(),
        "sample": state["scene_tensor_sample"],
        "program": state["selected_program"],
    }
    if state["program_bundle"]:
        body["program_bundle"] = state["program_bundle"]
    return body


# 对 health 响应做尽量轻量的 JSON 解析，解析失败不影响主执行。
def _safe_response_json(response: httpx.Response) -> Dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


# 生成失败 EvidencePack 的结构化 raw_trace 详情。
def _failure_details(
    *,
    error: HydroProgram3DError,
    base_url: str,
    request_summary: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "error": error.to_trace_data(),
        "base_url": base_url,
        "request_summary": request_summary,
    }


# 记录 hydro-program3d /health 结果；health 只用于诊断，不作为强阻断条件。
async def _check_health(state: AgentState, client: httpx.AsyncClient, base_url: str) -> None:
    started_at = _now()
    try:
        response = await client.get(f"{base_url}/health")
        duration_ms = _elapsed_ms(started_at)
        payload = _safe_response_json(response)
        append_trace(
            state,
            "execute_3d.health",
            "hydro-program3d health checked",
            {
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "ok": payload.get("ok"),
                "compiler_available": payload.get("compiler_available"),
                "nacos_registered": payload.get("nacos_registered"),
                "checkpoint_dir": payload.get("checkpoint_dir"),
            },
        )
    except Exception as exc:
        duration_ms = _elapsed_ms(started_at)
        error = classify_httpx_error("execute_3d.health", exc, duration_ms=duration_ms)
        append_trace(
            state,
            "execute_3d.health",
            "hydro-program3d health check skipped",
            error.to_trace_data(),
        )


# 从 HTTP 响应读取 JSON；如果响应体不是合法 JSON，就转成结构化错误。
def _json_payload(stage: str, response: httpx.Response, *, duration_ms: int) -> Dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise HydroProgram3DError(
            stage=stage,
            error_type="invalid_json",
            message=str(exc),
            retryable=False,
            status_code=response.status_code,
            duration_ms=duration_ms,
            response_text=response.text,
        ) from exc
    if not isinstance(payload, dict):
        raise HydroProgram3DError(
            stage=stage,
            error_type="invalid_json",
            message="response JSON root must be an object",
            retryable=False,
            status_code=response.status_code,
            duration_ms=duration_ms,
            response_text=response.text,
        )
    return payload


# 发送 POST JSON 请求，并对连接失败、超时和 5xx 做一次有限重试。
async def _post_json_with_retry(
    *,
    state: AgentState,
    client: httpx.AsyncClient,
    stage: str,
    url: str,
    body: Dict[str, Any],
) -> Dict[str, Any]:
    last_error: HydroProgram3DError | None = None
    for attempt in range(1, MAX_EXECUTE_ATTEMPTS + 1):
        started_at = _now()
        try:
            response = await client.post(url, json=body)
            duration_ms = _elapsed_ms(started_at)
            if response.status_code >= 300:
                raise http_status_error(stage, response, duration_ms=duration_ms)
            payload = _json_payload(stage, response, duration_ms=duration_ms)
            append_trace(
                state,
                stage,
                "hydro-program3d request succeeded",
                {
                    "attempt": attempt,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return payload
        except HydroProgram3DError as exc:
            last_error = exc
        except Exception as exc:
            last_error = classify_httpx_error(stage, exc, duration_ms=_elapsed_ms(started_at))

        should_retry = bool(last_error.retryable and attempt < MAX_EXECUTE_ATTEMPTS)
        append_trace(
            state,
            stage,
            "hydro-program3d request failed",
            {
                **last_error.to_trace_data(),
                "attempt": attempt,
                "will_retry": should_retry,
            },
        )
        if not should_retry:
            raise last_error

    # 这里理论上不会走到；保留兜底，避免类型检查和极端分支失控。
    if last_error is not None:
        raise last_error
    raise HydroProgram3DError(stage=stage, error_type="unknown", message="request failed")


# 从 /compile_evidence 响应中提取并校验 EvidencePack。
def _extract_evidence_pack(compile_payload: Dict[str, Any]) -> Dict[str, Any]:
    evidence_pack = compile_payload.get("evidence_pack", compile_payload)
    return validate_evidence_pack(evidence_pack)


# 执行 hydro-program3d 并把原始输出与 EvidencePack 写回 AgentState。
async def run_hydro_program3d(state: AgentState) -> AgentState:
    if state["status"] in {"FAILED", "ABSTAINED"}:
        state["evidence_pack"] = failure_evidence_pack(
            state["status"],
            {"error_type": "precondition_failed", "stage": "execute_3d"},
        )
        return state
    if not state["scene_tensor_sample"] or not state["selected_program"]:
        reason = "scene tensor sample or selected program is missing"
        append_error(state, "execute_3d", reason)
        state["evidence_pack"] = failure_evidence_pack(
            reason,
            {"error_type": "missing_execute_input", "stage": "execute_3d"},
        )
        state["status"] = "REVIEW_REQUIRED"
        return state

    execute_request = build_execute_request(state)
    request_summary = summarize_execute_request(execute_request)
    base_url = ""
    try:
        base_url = await resolve_http_base_url(HYDRO_PROGRAM3D_SERVICE_NAME, HYDRO_PROGRAM3D_URL)
        append_trace(
            state,
            "execute_3d.discovery",
            "hydro-program3d base url resolved",
            {
                "base_url": base_url,
                "service_name": HYDRO_PROGRAM3D_SERVICE_NAME,
                "direct_url_configured": bool(HYDRO_PROGRAM3D_URL),
            },
        )
        timeout = httpx.Timeout(HYDRO_PROGRAM3D_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            await _check_health(state, client, base_url)

            # /execute 保留原始模型输出，便于排查和复核。
            execute_payload = await _post_json_with_retry(
                state=state,
                client=client,
                stage="execute_3d.execute",
                url=f"{base_url}/execute",
                body=execute_request,
            )
            state["raw_executor_output"] = execute_payload
            state["status"] = "RAW_EXECUTOR_READY"

            # /compile_evidence 把原始输出转成风险层稳定消费的 EvidencePack。
            compile_payload = await _post_json_with_retry(
                state=state,
                client=client,
                stage="execute_3d.compile_evidence",
                url=f"{base_url}/compile_evidence",
                body=build_compile_request(state["scene_tensor_sample"], execute_payload),
            )
            evidence_pack = _extract_evidence_pack(compile_payload)
            state["evidence_pack"] = evidence_pack
            state["status"] = "EVIDENCE_READY"
            append_trace(
                state,
                "compile_evidence",
                "evidence pack compiled",
                {"confidence": evidence_pack.get("confidence")},
            )
    except HydroProgram3DError as exc:
        reason = str(exc)
        append_trace(
            state,
            exc.stage,
            "hydro-program3d execution failed",
            exc.to_trace_data(),
        )
        append_error(state, "execute_3d", reason, exc.to_trace_data())
        # 即使失败也统一补一个 EvidencePack 形状的对象，
        # 这样下游节点可以降级到 review-required，而不是直接崩掉。
        state["evidence_pack"] = failure_evidence_pack(
            reason,
            _failure_details(error=exc, base_url=base_url, request_summary=request_summary),
        )
        state["status"] = "REVIEW_REQUIRED"
    except Exception as exc:
        error = HydroProgram3DError(
            stage="execute_3d.discovery" if not base_url else "execute_3d",
            error_type="service_discovery_failed" if not base_url else "unexpected_error",
            message=str(exc),
            retryable=False,
        )
        reason = str(error)
        append_trace(
            state,
            error.stage,
            "hydro-program3d execution failed",
            error.to_trace_data(),
        )
        append_error(state, "execute_3d", reason, error.to_trace_data())
        state["evidence_pack"] = failure_evidence_pack(
            reason,
            _failure_details(error=error, base_url=base_url, request_summary=request_summary),
        )
        state["status"] = "REVIEW_REQUIRED"
    return state
