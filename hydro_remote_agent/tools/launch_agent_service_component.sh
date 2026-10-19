#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
RUN_DIR="${ROOT}/runs/hydro_remote_agent/agent_service_v1"
DB="${RUN_DIR}/jobs.sqlite"
COMPONENT="${1:?usage: launch_agent_service_component.sh api|planner|executor}"
GPU_ID="${GPU_ID:-0}"

mkdir -p "${RUN_DIR}"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"

case "${COMPONENT}" in
  api)
    PYTHON="python"
    exec "${PYTHON}" -m hydro_remote_agent.tools.agent_service_api \
      --db "${DB}" \
      --allowed-asset-root "${ROOT}/benchmark/10M" \
      --host "127.0.0.1" \
      --port "18080"
    ;;
  planner)
    PYTHON="python"
    export CUDA_VISIBLE_DEVICES="${GPU_ID}"
    exec "${PYTHON}" -m hydro_remote_agent.tools.agent_service_worker planner \
      --db "${DB}" \
      --model-path "/models/Qwen3-VL-8B-Instruct" \
      --adapter-path "${ROOT}/runs/hydro_remote_agent/qwen3_vl_8b_lora_v1" \
      --max-image-pixels 262144 \
      --lease-seconds "${LEASE_SECONDS:-1800}" \
      --worker-id "planner_gpu${GPU_ID}"
    ;;
  executor)
    PYTHON="python"
    export CUDA_VISIBLE_DEVICES="${GPU_ID}"
    exec "${PYTHON}" -m hydro_remote_agent.tools.agent_service_worker executor \
      --db "${DB}" \
      --expert-work-dir "${RUN_DIR}/expert_outputs" \
      --execution-work-dir "${RUN_DIR}/agent_executions" \
      --lease-seconds "${LEASE_SECONDS:-120}" \
      --worker-id "executor_gpu${GPU_ID}"
    ;;
  *)
    echo "Unknown component: ${COMPONENT}" >&2
    exit 2
    ;;
esac
