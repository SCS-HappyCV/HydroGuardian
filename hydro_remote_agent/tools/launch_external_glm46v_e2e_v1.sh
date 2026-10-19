#!/usr/bin/env bash
set -euo pipefail

ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
PYTHON="${HYDRO_GLM_PYTHON:-/opt/venvs/glm46v-agent/bin/python}"
PLANNER_GPU="${PLANNER_GPU:?Set PLANNER_GPU after checking nvidia-smi}"
MIN_FREE_MIB="${MIN_FREE_MIB:-36000}"
EXPERT_URL="${EXPERT_URL:-http://127.0.0.1:19091}"
RUN_DIR="${RUN_DIR:-${ROOT}/runs/hydro_remote_agent/external_baselines_v1/glm46v_flash_toolspec}"
GOLD="${ROOT}/runs/hydro_remote_agent/agent_e2e_comparison_v1/gold_50.jsonl"
MODEL_PATH="${MODEL_PATH:-}"

used_mib="$(nvidia-smi --id="${PLANNER_GPU}" --query-gpu=memory.used --format=csv,noheader,nounits)"
total_mib="$(nvidia-smi --id="${PLANNER_GPU}" --query-gpu=memory.total --format=csv,noheader,nounits)"
free_mib="$((total_mib - used_mib))"
if (( free_mib < MIN_FREE_MIB )); then
  echo "GLM_GPU_PREFLIGHT_FAILED gpu=${PLANNER_GPU} free_mib=${free_mib} required_mib=${MIN_FREE_MIB}" >&2
  exit 2
fi

if [[ ! -f "${ROOT}/models/GLM-4.6V-Flash/vaguehydro_external_model_manifest.json" \
      && ! -f "/models/GLM-4.6V-Flash/vaguehydro_external_model_manifest.json" ]]; then
  echo "GLM_MODEL_MANIFEST_MISSING" >&2
  exit 3
fi

mkdir -p "${RUN_DIR}"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"
export CUDA_VISIBLE_DEVICES="${PLANNER_GPU}"

ARGS=(
  --config "${ROOT}/hydro_remote_agent/configs/external_glm46v_flash.json" \
  --input "${GOLD}" \
  --output "${RUN_DIR}/run_50.jsonl" \
  --expert-base-url "${EXPERT_URL}" \
  --expert-work-dir "${RUN_DIR}/remote_client" \
  --execution-work-dir "${RUN_DIR}/executions" \
  --max-new-tokens 1024 \
  --max-image-pixels 262144 \
  --resume
)
if [[ -n "${MODEL_PATH}" ]]; then
  ARGS+=(--model-path "${MODEL_PATH}")
elif [[ -f /tmp/vague_hydro_cache/model/GLM-4.6V-Flash/vaguehydro_external_model_manifest.json ]]; then
  ARGS+=(--model-path /tmp/vague_hydro_cache/model/GLM-4.6V-Flash)
fi

exec "${PYTHON}" -u -m hydro_remote_agent.tools.run_external_vlm_e2e_condition \
  "${ARGS[@]}" "$@"
