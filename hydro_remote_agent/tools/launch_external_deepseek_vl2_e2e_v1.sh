#!/usr/bin/env bash
set -euo pipefail

ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
PYTHON="${HYDRO_DEEPSEEK_PYTHON:-/opt/venvs/deepseek-vl2-agent/bin/python}"
PLANNER_GPU="${PLANNER_GPU:?Set PLANNER_GPU after checking nvidia-smi}"
MIN_FREE_MIB="${MIN_FREE_MIB:-40000}"
EXPERT_URL="${EXPERT_URL:-http://127.0.0.1:19091}"
RUN_DIR="${RUN_DIR:-${ROOT}/runs/hydro_remote_agent/external_deepseek_vl2_v1/deepseek_vl2_small_toolspec}"
GOLD="${ROOT}/runs/hydro_remote_agent/agent_e2e_comparison_v1/gold_50.jsonl"
MODEL_PATH="${MODEL_PATH:-/models/deepseek-vl2-small}"

used_mib="$(nvidia-smi --id="${PLANNER_GPU}" --query-gpu=memory.used --format=csv,noheader,nounits)"
total_mib="$(nvidia-smi --id="${PLANNER_GPU}" --query-gpu=memory.total --format=csv,noheader,nounits)"
free_mib="$((total_mib - used_mib))"
if (( free_mib < MIN_FREE_MIB )); then
  echo "DEEPSEEK_VL2_GPU_PREFLIGHT_FAILED gpu=${PLANNER_GPU} free_mib=${free_mib} required_mib=${MIN_FREE_MIB}" >&2
  exit 2
fi
if [[ ! -f "${MODEL_PATH}/vaguehydro_external_model_manifest.json" ]]; then
  echo "DEEPSEEK_VL2_MODEL_MANIFEST_MISSING path=${MODEL_PATH}" >&2
  exit 3
fi

mkdir -p "${RUN_DIR}"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"
export CUDA_VISIBLE_DEVICES="${PLANNER_GPU}"
export TOKENIZERS_PARALLELISM=false
exec "${PYTHON}" -u -m hydro_remote_agent.tools.run_external_vlm_e2e_condition \
  --config "${ROOT}/hydro_remote_agent/configs/external_deepseek_vl2_small.json" \
  --input "${GOLD}" \
  --output "${RUN_DIR}/run_50.jsonl" \
  --model-path "${MODEL_PATH}" \
  --expert-base-url "${EXPERT_URL}" \
  --expert-work-dir "${RUN_DIR}/remote_client" \
  --execution-work-dir "${RUN_DIR}/executions" \
  --max-new-tokens 1024 \
  --max-image-pixels 262144 \
  --resume "$@"
