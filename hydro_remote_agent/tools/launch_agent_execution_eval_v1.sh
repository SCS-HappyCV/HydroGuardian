#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
PYTHON="${PYTHON:-python}"
RUN_NAME="${RUN_NAME:-agent_execution_eval_v1}"
GPU_ID="${GPU_ID:-0}"
MAX_EXPERT_EXECUTIONS="${MAX_EXPERT_EXECUTIONS:-}"
RUN_DIR="${ROOT}/runs/hydro_remote_agent/${RUN_NAME}"

mkdir -p "${RUN_DIR}"
export CUDA_VISIBLE_DEVICES="${GPU_ID}"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"

ARGS=(
  --predictions "${ROOT}/runs/hydro_remote_agent/agent_eval_v1/adapter_predictions_240.jsonl"
  --output "${RUN_DIR}/execution_results.jsonl"
  --report "${RUN_DIR}/execution_report.json"
  --registry "${ROOT}/hydro_remote_agent/configs/tool_registry.yaml"
  --runtime "${ROOT}/hydro_remote_agent/configs/expert_runtime.yaml"
  --expert-work-dir "${RUN_DIR}/expert_outputs"
  --execution-work-dir "${RUN_DIR}/agent_executions"
)
if [[ -n "${MAX_EXPERT_EXECUTIONS}" ]]; then
  ARGS+=(--max-expert-executions "${MAX_EXPERT_EXECUTIONS}")
fi

set +e
"${PYTHON}" -m hydro_remote_agent.tools.evaluate_agent_execution "${ARGS[@]}" \
  2>&1 | tee -a "${RUN_DIR}/execution.log"
STATUS=${PIPESTATUS[0]}
set -e
printf '%s\n' "${STATUS}" > "${RUN_DIR}/exit_code.txt"
exit "${STATUS}"
