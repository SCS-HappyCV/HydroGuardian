#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
PYTHON_BIN="${EXPERT_PYTHON:-python}"
ENV_FILE="${EXPERT_ENV_FILE:-${PROJECT_ROOT}/hydro_remote_agent/deploy/.env.cpu-worker}"

set -a
source "${ENV_FILE}"
set +a
cd "${PROJECT_ROOT}"

exec "${PYTHON_BIN}" -u -m hydro_remote_agent.tools.expert_worker_ws \
  --agent-ws-url "${AGENT_WS_URL:-ws://127.0.0.1:28080/internal/workers/ws}" \
  --runtime hydro_remote_agent/configs/expert_runtime.cpu.yaml \
  --work-dir hydro_remote_agent/runs/expert_runtime_cpu_worker \
  --worker-id "${WORKER_ID:-gpu-worker-cpu-geometry}" \
  --worker-version "${WORKER_VERSION:-cpu-v1}" \
  --capability geometry_relation_analysis \
  --capability result_quality_verification \
  --minio-endpoint "${MINIO_ENDPOINT:-127.0.0.1:29000}"
