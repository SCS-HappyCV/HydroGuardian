#!/usr/bin/env bash
set -euo pipefail

ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
PYTHON="${HYDRO_AGENT_PYTHON:-python}"
INTERNAL_ROOT="${INTERNAL_ROOT:-${ROOT}/runs/hydro_remote_agent/agent_e2e_comparison_v1}"
EXTERNAL_ROOT="${EXTERNAL_ROOT:-${ROOT}/runs/hydro_remote_agent/external_baselines_v1}"
ORACLE_ROOT="${ORACLE_ROOT:-${ROOT}/runs/hydro_remote_agent/oracle_gold_routing_v1}"
ANNOTATIONS="${ANNOTATIONS:-${ROOT}/data/wcs2d3d_lang_v4_llm_auto_cross_region_train_dashscope_en_v2.jsonl}"
DATA_ROOT="${DATA_ROOT:-${ROOT}/benchmark/10M}"

GOLD="${INTERNAL_ROOT}/gold_50.jsonl"
REACT_RUN="${INTERNAL_ROOT}/tool_observation_react/run_50.jsonl"
GLM_RUN="${EXTERNAL_ROOT}/glm46v_flash_toolspec/run_50.jsonl"
LORA_RUN="${INTERNAL_ROOT}/vaguehydro_lora/run_50.jsonl"
ORACLE_RUN="${ORACLE_ROOT}/oracle_gold_routing/run_50.jsonl"

for required in "${GOLD}" "${REACT_RUN}" "${GLM_RUN}" "${LORA_RUN}" "${ORACLE_RUN}" "${ANNOTATIONS}"; do
  if [[ ! -f "${required}" ]]; then
    echo "ORACLE_ANALYSIS_INPUT_MISSING path=${required}" >&2
    exit 2
  fi
done

mkdir -p "${ORACLE_ROOT}/task_aware_quality_v1"
cd "${ROOT}"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"

"${PYTHON}" -m hydro_remote_agent.tools.compare_agent_e2e \
  --gold "${GOLD}" \
  --condition tool_observation_react "${REACT_RUN}" \
  --condition glm46v_flash_toolspec "${GLM_RUN}" \
  --condition vaguehydro_lora "${LORA_RUN}" \
  --condition oracle_gold_routing "${ORACLE_RUN}" \
  --reference oracle_gold_routing \
  --output "${ORACLE_ROOT}/comparison_report.json"

"${PYTHON}" -m hydro_remote_agent.tools.evaluate_agent_task_quality \
  --gold "${GOLD}" \
  --annotations "${ANNOTATIONS}" \
  --data-root "${DATA_ROOT}" \
  --condition tool_observation_react "${REACT_RUN}" \
  --condition glm46v_flash_toolspec "${GLM_RUN}" \
  --condition vaguehydro_lora "${LORA_RUN}" \
  --condition oracle_gold_routing "${ORACLE_RUN}" \
  --reference oracle_gold_routing \
  --bootstrap-samples 10000 \
  --bootstrap-seed 20260809 \
  --output-dir "${ORACLE_ROOT}/task_aware_quality_v1" \
  --report "${ORACLE_ROOT}/task_aware_quality_v1/report.json"

echo "ORACLE_GOLD_ROUTING_ANALYSIS_OK root=${ORACLE_ROOT}"
