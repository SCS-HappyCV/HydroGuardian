#!/usr/bin/env bash
set -euo pipefail

ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
PYTHON="${HYDRO_AGENT_PYTHON:-python}"
INTERNAL_ROOT="${INTERNAL_ROOT:-${ROOT}/runs/hydro_remote_agent/agent_e2e_comparison_v1}"
GLM_ROOT="${GLM_ROOT:-${ROOT}/runs/hydro_remote_agent/external_baselines_v1}"
DEEPSEEK_ROOT="${DEEPSEEK_ROOT:-${ROOT}/runs/hydro_remote_agent/external_deepseek_vl2_v1}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${ROOT}/runs/hydro_remote_agent/external_agent_comparison_v2}"
ANNOTATIONS="${ANNOTATIONS:-${ROOT}/data/wcs2d3d_lang_v4_llm_auto_cross_region_train_dashscope_en_v2.jsonl}"
DATA_ROOT="${DATA_ROOT:-${ROOT}/benchmark/10M}"

GOLD="${INTERNAL_ROOT}/gold_50.jsonl"
REACT_RUN="${INTERNAL_ROOT}/tool_observation_react/run_50.jsonl"
GLM_RUN="${GLM_ROOT}/glm46v_flash_toolspec/run_50.jsonl"
DEEPSEEK_RUN="${DEEPSEEK_ROOT}/deepseek_vl2_small_toolspec/run_50.jsonl"
LORA_RUN="${INTERNAL_ROOT}/vaguehydro_lora/run_50.jsonl"

for required in "${GOLD}" "${REACT_RUN}" "${GLM_RUN}" "${DEEPSEEK_RUN}" "${LORA_RUN}" "${ANNOTATIONS}"; do
  if [[ ! -f "${required}" ]]; then
    echo "EXTERNAL_V2_ANALYSIS_INPUT_MISSING path=${required}" >&2
    exit 2
  fi
done

mkdir -p "${OUTPUT_ROOT}/task_aware_quality_v1" "${OUTPUT_ROOT}/model_manifests"
for manifest in \
  "${GLM_ROOT}/model_manifest.json" \
  "/models/deepseek-vl2-small/vaguehydro_external_model_manifest.json"; do
  if [[ -f "${manifest}" ]]; then
    cp "${manifest}" "${OUTPUT_ROOT}/model_manifests/$(basename "$(dirname "${manifest}")")_manifest.json"
  fi
done

cd "${ROOT}"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"

CONDITIONS=(
  --condition tool_observation_react "${REACT_RUN}"
  --condition glm46v_flash_toolspec "${GLM_RUN}"
  --condition deepseek_vl2_small_toolspec "${DEEPSEEK_RUN}"
  --condition vaguehydro_lora "${LORA_RUN}"
)

"${PYTHON}" -m hydro_remote_agent.tools.compare_agent_e2e \
  --gold "${GOLD}" "${CONDITIONS[@]}" \
  --reference vaguehydro_lora \
  --output "${OUTPUT_ROOT}/comparison_report.json"

"${PYTHON}" -m hydro_remote_agent.tools.evaluate_agent_task_quality \
  --gold "${GOLD}" \
  --annotations "${ANNOTATIONS}" \
  --data-root "${DATA_ROOT}" \
  "${CONDITIONS[@]}" \
  --reference vaguehydro_lora \
  --bootstrap-samples 10000 \
  --bootstrap-seed 20260810 \
  --output-dir "${OUTPUT_ROOT}/task_aware_quality_v1" \
  --report "${OUTPUT_ROOT}/task_aware_quality_v1/report.json"

echo "EXTERNAL_AGENT_COMPARISON_V2_OK root=${OUTPUT_ROOT}"
