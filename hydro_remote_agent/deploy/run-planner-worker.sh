#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
PYTHON_BIN="${PLANNER_PYTHON:-python}"
ENV_FILE="${PLANNER_ENV_FILE:-${PROJECT_ROOT}/hydro_remote_agent/deploy/.env.cpu-worker}"
PLANNER_GPU_ID="${PLANNER_GPU_ID:-0}"

set -a
source "${ENV_FILE}"
set +a
cd "${PROJECT_ROOT}"

export CUDA_VISIBLE_DEVICES="${PLANNER_GPU_ID}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PLANNER_MAX_SOURCE_IMAGE_PIXELS="${PLANNER_MAX_SOURCE_IMAGE_PIXELS:-350000000}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

exec "${PYTHON_BIN}" -u -m hydro_remote_agent.tools.remote_planner_worker \
  --agent-base-url "${AGENT_BASE_URL:-http://127.0.0.1:28080}" \
  --asset-base-url "${ASSET_BASE_URL:-http://127.0.0.1:28080}" \
  --worker-id "${PLANNER_WORKER_ID:-qwen3-vl-planner-gpu0}" \
  --registry hydro_remote_agent/configs/tool_registry.yaml \
  --model-path "${PLANNER_MODEL_PATH:-/models/Qwen3-VL-8B-Instruct}" \
  --adapter-path "${PLANNER_ADAPTER_PATH:-${PROJECT_ROOT}/runs/hydro_remote_agent/qwen3_vl_8b_lora_v1}" \
  --max-new-tokens "${PLANNER_MAX_NEW_TOKENS:-640}" \
  --max-image-pixels "${PLANNER_MAX_IMAGE_PIXELS:-196608}"
