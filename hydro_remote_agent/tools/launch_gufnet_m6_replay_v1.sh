#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/workspace/HydroGuardian}"
PYTHON="${PYTHON:-python}"
GPU="${GPU:-1}"
GUFNET_URL="${GUFNET_URL:-http://127.0.0.1:19109}"
RUN_ROOT="${RUN_ROOT:-${ROOT}/runs/hydro_remote_agent/expert_replacement_v1/gufnet_m6_replay_v1}"
GOLD="${ROOT}/runs/hydro_remote_agent/agent_eval_v1/gold_240.jsonl"
ANNOTATIONS="${ROOT}/data/wcs2d3d_lang_v4_llm_auto_cross_region_train_dashscope_en_v2.jsonl"
DATA_ROOT="${ROOT}/benchmark/10M"

# Oracle runs first and becomes a GUFNet-only cache for identical requests in
# the other frozen conditions. PTv3 execution caches must never be reused here.
conditions=(
  oracle_gold_routing
  tool_observation_react
  vaguehydro_lora
  rule_router
  glm46v_flash_toolspec
  deepseek_vl2_small_schema_constrained
)
sources=(
  runs/hydro_remote_agent/agent_task_aware_e2e_240/oracle_gold_routing/run_240.jsonl
  runs/hydro_remote_agent/agent_task_aware_e2e_240/tool_observation_react/run_240.jsonl
  runs/hydro_remote_agent/agent_task_aware_e2e_240/vaguehydro_lora/run_240.jsonl
  runs/hydro_remote_agent/hydro_agent_bench_gate_v1/rule_router/run_240.jsonl
  runs/hydro_remote_agent/agent_task_aware_e2e_240/glm46v_flash_toolspec/run_240.jsonl
  runs/hydro_remote_agent/agent_task_aware_e2e_240/deepseek_vl2_small_schema_constrained/run_240.jsonl
)
hashes=(
  148711331fb906fb429c55526b18270f08e8030e3fba61ec5f72bed84cf9c074
  43deb410bf756b3e4decce37fab5cf4eeabb163e60475289bd5f70c7ede44f1b
  741659bd1b79b5b2704c48b04c392afdc5abcb77efe8ce94ffc04e59be29cf75
  de9e0ebc8c826842b9d5accc79f9f5c8e1e4bd95af04f81a97870f3ccef5bfb3
  2bf5dffbe784f4721d10266d589eb320ab50c25943d0de73ebf56110657b4e37
  e6508ae0ec6118c1540961e5be1236419de408f12ae4e9216dbe89bdb067bd85
)

mkdir -p "${RUN_ROOT}"
cd "${ROOT}"
curl --fail --silent --show-error "${GUFNET_URL}/healthz" > "${RUN_ROOT}/gufnet_health_at_launch.json"

oracle_cache="${RUN_ROOT}/oracle_gold_routing/run_240.jsonl"
for index in "${!conditions[@]}"; do
  condition="${conditions[$index]}"
  source="${ROOT}/${sources[$index]}"
  expected_sha="${hashes[$index]}"
  actual_sha="$(sha256sum "${source}" | awk '{print $1}')"
  if [[ "${actual_sha}" != "${expected_sha}" ]]; then
    echo "M6_FROZEN_INPUT_HASH_MISMATCH condition=${condition} expected=${expected_sha} actual=${actual_sha}" >&2
    exit 2
  fi

  reuse_args=()
  if [[ "${condition}" != "oracle_gold_routing" ]]; then
    reuse_args=(--reuse-run "${oracle_cache}")
  fi
  mkdir -p "${RUN_ROOT}/${condition}"
  CUDA_VISIBLE_DEVICES="${GPU}" HF_HUB_OFFLINE=1 PYTHONPATH=. \
    "${PYTHON}" -u -m hydro_remote_agent.tools.replay_frozen_agent_condition \
    --input "${source}" \
    --expected-input-sha256 "${expected_sha}" \
    --output "${RUN_ROOT}/${condition}/run_240.jsonl" \
    --condition "${condition}" \
    --runtime hydro_remote_agent/configs/expert_runtime.hydro_agent_bench_downstream.yaml \
    --tool-base-url "point_semantic_segmentation=${GUFNET_URL}" \
    --tool-alias multimodal_semantic_segmentation=point_semantic_segmentation \
    --replacement-tool multimodal_semantic_segmentation \
    --replacement-tool point_semantic_segmentation \
    "${reuse_args[@]}" \
    --expert-work-dir "${RUN_ROOT}/${condition}/expert_runtime" \
    --execution-work-dir "${RUN_ROOT}/${condition}/executions" \
    --resume
done

"${PYTHON}" -u -m hydro_remote_agent.tools.evaluate_agent_task_quality \
  --gold "${GOLD}" \
  --annotations "${ANNOTATIONS}" \
  --data-root "${DATA_ROOT}" \
  --condition rule_router "${RUN_ROOT}/rule_router/run_240.jsonl" \
  --condition tool_observation_react "${RUN_ROOT}/tool_observation_react/run_240.jsonl" \
  --condition glm46v_flash_toolspec "${RUN_ROOT}/glm46v_flash_toolspec/run_240.jsonl" \
  --condition deepseek_vl2_small_schema_constrained "${RUN_ROOT}/deepseek_vl2_small_schema_constrained/run_240.jsonl" \
  --condition vaguehydro_lora "${RUN_ROOT}/vaguehydro_lora/run_240.jsonl" \
  --condition oracle_gold_routing "${RUN_ROOT}/oracle_gold_routing/run_240.jsonl" \
  --output-dir "${RUN_ROOT}/task_quality" \
  --report "${RUN_ROOT}/task_quality/report.json" \
  --bootstrap-samples 10000 \
  --reference vaguehydro_lora

"${PYTHON}" -u -m hydro_remote_agent.tools.analyze_hydro_agent_bench \
  --config hydro_remote_agent/configs/hydro_agent_bench_protocol_gufnet_m6.json \
  --output "${RUN_ROOT}/analysis/formal_analysis.json" \
  --markdown "${RUN_ROOT}/analysis/FORMAL_ANALYSIS.md"

echo "GUFNET_M6_REPLAY_OK root=${RUN_ROOT}"
