#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
PYTHON="${PYTHON:-python}"
GPU_ID="${GPU_ID:-4}"
RUN_NAME="${RUN_NAME:-full200}"
MAX_EXPERT_EXECUTIONS="${MAX_EXPERT_EXECUTIONS:-}"
BASE_DIR="${RUN_BASE_DIR:-${ROOT}/runs/cmge_planner_v1/test100_unseen/expert_replacement_ptv3}"
RUN_DIR="${BASE_DIR}/${RUN_NAME}"
PREDICTIONS="${PREDICTIONS:-${BASE_DIR}/changed_predictions.jsonl}"

mkdir -p "${RUN_DIR}"
export CUDA_VISIBLE_DEVICES="${GPU_ID}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"

ARGS=(
  --predictions "${PREDICTIONS}"
  --output "${RUN_DIR}/execution_results.jsonl"
  --report "${RUN_DIR}/execution_report.json"
  --registry "${ROOT}/hydro_remote_agent/configs/tool_registry.yaml"
  --runtime "${ROOT}/hydro_remote_agent/configs/expert_runtime.pointcept_hydro_agent_bench.yaml"
  --expert-work-dir "${RUN_DIR}/expert_outputs"
  --execution-work-dir "${RUN_DIR}/agent_executions"
)
if [[ -n "${MAX_EXPERT_EXECUTIONS}" ]]; then
  ARGS+=(--max-expert-executions "${MAX_EXPERT_EXECUTIONS}")
fi

cd "${ROOT}"
set +e
"${PYTHON}" -m hydro_remote_agent.tools.evaluate_agent_execution "${ARGS[@]}" \
  2>&1 | tee -a "${RUN_DIR}/execution.log"
STATUS=${PIPESTATUS[0]}
set -e
printf '%s\n' "${STATUS}" > "${RUN_DIR}/exit_code.txt"
exit "${STATUS}"
