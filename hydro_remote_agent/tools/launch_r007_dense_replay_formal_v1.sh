#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/workspace/HydroGuardian}"
PYTHON="${PYTHON:-python}"
GPU="${GPU:-5}"
PTV3_URL="${PTV3_URL:-http://127.0.0.1:19107}"
RUN_ROOT="${RUN_ROOT:-${ROOT}/runs/hydro_remote_agent/expert_replacement_v1/r007_dense_replay_formal_v1}"
GOLD="${ROOT}/runs/hydro_remote_agent/agent_eval_v1/gold_240.jsonl"
GOLD_SHA256="58c9c016d129c014179cd717739d48ef0e2c0017e1ad37e3374c246b13882b67"
ANNOTATIONS="${ROOT}/data/wcs2d3d_lang_v4_llm_auto_cross_region_train_dashscope_en_v2.jsonl"
DATA_ROOT="${ROOT}/benchmark/10M"
RUN_OUTPUT="${RUN_ROOT}/oracle_dense/run_160.jsonl"
DENSE_GOLD="${RUN_ROOT}/oracle_dense/gold_dense_160.jsonl"

mkdir -p "${RUN_ROOT}/oracle_dense" "${RUN_ROOT}/expert_runtime" "${RUN_ROOT}/executions"
cd "${ROOT}"

curl --fail --silent --show-error "${PTV3_URL}/healthz" > "${RUN_ROOT}/ptv3_health_at_launch.json"

"${PYTHON}" -m hydro_remote_agent.tools.select_jsonl_records \
  --input "${GOLD}" \
  --output "${DENSE_GOLD}" \
  --action-type tool_call \
  --action-type workflow \
  --expected-input-sha256 "${GOLD_SHA256}" \
  --expected-count 160

CUDA_VISIBLE_DEVICES="${GPU}" HF_HUB_OFFLINE=1 PYTHONPATH=. \
  "${PYTHON}" -u -m hydro_remote_agent.tools.run_oracle_e2e_condition \
  --input "${GOLD}" \
  --expected-input-sha256 "${GOLD_SHA256}" \
  --output "${RUN_OUTPUT}" \
  --runtime hydro_remote_agent/configs/expert_runtime.hydro_agent_bench_downstream.yaml \
  --tool-base-url "point_semantic_segmentation=${PTV3_URL}" \
  --expert-work-dir "${RUN_ROOT}/expert_runtime" \
  --execution-work-dir "${RUN_ROOT}/executions" \
  --action-type tool_call \
  --action-type workflow \
  --tool-alias multimodal_semantic_segmentation=point_semantic_segmentation \
  --resume

"${PYTHON}" -m hydro_remote_agent.tools.select_jsonl_records \
  --input "${GOLD}" \
  --output "${DENSE_GOLD}" \
  --ids-from "${RUN_OUTPUT}" \
  --expected-input-sha256 "${GOLD_SHA256}" \
  --expected-count 160

"${PYTHON}" -u -m hydro_remote_agent.tools.evaluate_agent_task_quality \
  --gold "${DENSE_GOLD}" \
  --annotations "${ANNOTATIONS}" \
  --data-root "${DATA_ROOT}" \
  --condition r007_ptv3_hybrid "${RUN_OUTPUT}" \
  --output-dir "${RUN_ROOT}/task_quality" \
  --report "${RUN_ROOT}/task_quality/report.json" \
  --bootstrap-samples 10000

echo "R007_DENSE_REPLAY_OK output=${RUN_OUTPUT} report=${RUN_ROOT}/task_quality/report.json"
