from __future__ import annotations

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
from discovery import resolve_http_base_url
from state import AgentState, append_error, append_trace, failure_evidence_pack


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


async def run_hydro_program3d(state: AgentState) -> AgentState:
    if state["status"] in {"FAILED", "ABSTAINED"}:
        state["evidence_pack"] = failure_evidence_pack(state["status"])
        return state
    if not state["scene_tensor_sample"] or not state["selected_program"]:
        reason = "scene tensor sample or selected program is missing"
        append_error(state, "execute_3d", reason)
        state["evidence_pack"] = failure_evidence_pack(reason)
        state["status"] = "REVIEW_REQUIRED"
        return state

    try:
        base_url = await resolve_http_base_url(HYDRO_PROGRAM3D_SERVICE_NAME, HYDRO_PROGRAM3D_URL)
        timeout = httpx.Timeout(HYDRO_PROGRAM3D_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                # health 只做参考，不作为强阻断条件。
                # 有些半联通部署 health 会偏保守，但 execute 仍可能可用。
                health = await client.get(f"{base_url}/health")
                append_trace(
                    state,
                    "execute_3d.health",
                    "hydro-program3d health checked",
                    {"status_code": health.status_code},
                )
            except Exception as exc:
                append_trace(state, "execute_3d.health", f"health check skipped: {exc}")

            # /execute 保留原始模型输出，便于排查；
            # /compile_evidence 再把它转成下游稳定消费的 EvidencePack。
            execute_resp = await client.post(f"{base_url}/execute", json=build_execute_request(state))
            if execute_resp.status_code >= 300:
                raise RuntimeError(f"/execute {execute_resp.status_code}: {execute_resp.text[:500]}")
            execute_payload = execute_resp.json()
            state["raw_executor_output"] = execute_payload
            state["status"] = "RAW_EXECUTOR_READY"

            compile_resp = await client.post(
                f"{base_url}/compile_evidence",
                json={
                    "sample": state["scene_tensor_sample"],
                    "execution_result": execute_payload,
                    "batch_index": 0,
                },
            )
            if compile_resp.status_code >= 300:
                raise RuntimeError(f"/compile_evidence {compile_resp.status_code}: {compile_resp.text[:500]}")
            compile_payload = compile_resp.json()
            evidence_pack = compile_payload.get("evidence_pack", compile_payload)
            if not isinstance(evidence_pack, dict):
                raise RuntimeError("/compile_evidence returned invalid evidence_pack")
            state["evidence_pack"] = evidence_pack
            state["status"] = "EVIDENCE_READY"
            append_trace(
                state,
                "compile_evidence",
                "evidence pack compiled",
                {"confidence": evidence_pack.get("confidence")},
            )
    except Exception as exc:
        reason = str(exc)
        append_error(state, "execute_3d", reason)
        # 即使失败也统一补一个 EvidencePack 形状的对象，
        # 这样下游节点可以降级到 review-required，而不是直接崩掉。
        state["evidence_pack"] = failure_evidence_pack(reason)
        state["status"] = "REVIEW_REQUIRED"
    return state
