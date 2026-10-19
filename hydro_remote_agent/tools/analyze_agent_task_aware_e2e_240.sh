#!/usr/bin/env bash
set -euo pipefail

ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
PYTHON="${HYDRO_AGENT_PYTHON:-python}"
RUN_ROOT="${RUN_ROOT:-${ROOT}/runs/hydro_remote_agent/agent_task_aware_e2e_240}"
GOLD="${ROOT}/runs/hydro_remote_agent/agent_eval_v1/gold_240.jsonl"
ANNOTATIONS="${ROOT}/data/wcs2d3d_lang_v4_llm_auto_cross_region_train_dashscope_en_v2.jsonl"
DATA_ROOT="${ROOT}/benchmark/10M"

CONDITIONS=(
  --condition tool_observation_react "${RUN_ROOT}/tool_observation_react/run_240.jsonl"
  --condition glm46v_flash_toolspec "${RUN_ROOT}/glm46v_flash_toolspec/run_240.jsonl"
  --condition deepseek_vl2_small_schema_constrained "${RUN_ROOT}/deepseek_vl2_small_schema_constrained/run_240.jsonl"
  --condition vaguehydro_lora "${RUN_ROOT}/vaguehydro_lora/run_240.jsonl"
  --condition oracle_gold_routing "${RUN_ROOT}/oracle_gold_routing/run_240.jsonl"
)

for ((index=2; index<${#CONDITIONS[@]}; index+=3)); do
  path="${CONDITIONS[index]}"
  if [[ ! -f "${path}" ]]; then
    echo "TASK_AWARE_240_INPUT_MISSING path=${path}" >&2
    exit 2
  fi
done

mkdir -p "${RUN_ROOT}/task_aware_quality_v1"
cd "${ROOT}"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"

"${PYTHON}" -m hydro_remote_agent.tools.compare_agent_e2e \
  --gold "${GOLD}" \
  "${CONDITIONS[@]}" \
  --reference vaguehydro_lora \
  --output "${RUN_ROOT}/comparison_report.json"

"${PYTHON}" -m hydro_remote_agent.tools.evaluate_agent_task_quality \
  --gold "${GOLD}" \
  --annotations "${ANNOTATIONS}" \
  --data-root "${DATA_ROOT}" \
  "${CONDITIONS[@]}" \
  --reference vaguehydro_lora \
  --bootstrap-samples 10000 \
  --bootstrap-seed 20260811 \
  --output-dir "${RUN_ROOT}/task_aware_quality_v1" \
  --report "${RUN_ROOT}/task_aware_quality_v1/report.json"

echo "AGENT_TASK_AWARE_E2E_240_ANALYSIS_OK root=${RUN_ROOT}"
