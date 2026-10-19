#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
RUN_DIR="${ROOT}/runs/hydro_remote_agent/agent_e2e_comparison_v1"
PYTHON="python"
CONDITION="${1:?usage: launch_agent_e2e_comparison_v1.sh tool_observation_react|vaguehydro_lora}"
PLANNER_GPU="${PLANNER_GPU:-2}"
EXPERT_URL="${EXPERT_URL:-http://127.0.0.1:19091}"

mkdir -p "${RUN_DIR}/${CONDITION}"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"
export CUDA_VISIBLE_DEVICES="${PLANNER_GPU}"

ARGS=(
  --condition "${CONDITION}"
  --config "${ROOT}/hydro_remote_agent/configs/backbone_qwen3_vl_8b.json"
  --input "${RUN_DIR}/gold_50.jsonl"
  --output "${RUN_DIR}/${CONDITION}/run_50.jsonl"
  --expert-base-url "${EXPERT_URL}"
  --expert-work-dir "${RUN_DIR}/${CONDITION}/remote_client"
  --execution-work-dir "${RUN_DIR}/${CONDITION}/executions"
  --max-image-pixels 262144
  --resume
)

if [[ "${CONDITION}" == "vaguehydro_lora" ]]; then
  ARGS+=(--adapter-path "${ROOT}/runs/hydro_remote_agent/qwen3_vl_8b_lora_v1")
fi

exec "${PYTHON}" -u -m hydro_remote_agent.tools.run_agent_e2e_condition "${ARGS[@]}"
