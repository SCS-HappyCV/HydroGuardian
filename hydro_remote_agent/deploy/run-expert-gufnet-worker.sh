#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
PYTHON_BIN="${EXPERT_PYTHON:-python}"
ENV_FILE="${EXPERT_ENV_FILE:-${PROJECT_ROOT}/hydro_remote_agent/deploy/.env.cpu-worker}"
EXPERT_GPU_ID="${EXPERT_GPU_ID:-2}"

set -a
source "${ENV_FILE}"
set +a
cd "${PROJECT_ROOT}"

export CUDA_VISIBLE_DEVICES="${EXPERT_GPU_ID}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
exec "${PYTHON_BIN}" -u -m hydro_remote_agent.tools.expert_worker_ws \
  --agent-ws-url "${AGENT_WS_URL:-ws://127.0.0.1:28080/internal/workers/ws}" \
  --runtime hydro_remote_agent/configs/expert_runtime.gufnet.yaml \
  --work-dir hydro_remote_agent/runs/expert_runtime_gufnet_worker \
  --worker-id "${WORKER_ID:-gpu-worker-gufnet-gpu2}" \
  --worker-version "${WORKER_VERSION:-gufnet-v1}" \
  --capability point_semantic_segmentation \
  --minio-endpoint "${MINIO_ENDPOINT:-127.0.0.1:29000}"
