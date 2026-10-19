#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
PYTHON="python"
RUN_DIR="${ROOT}/runs/hydro_remote_agent/agent_multi_baseline_v1"
GOLD="${ROOT}/runs/hydro_remote_agent/agent_eval_v1/gold_240.jsonl"
MODEL_PATH="/models/Qwen3-VL-8B-Instruct"
BACKBONE_CONFIG="hydro_remote_agent/configs/backbone_qwen3_vl_8b.json"
PROTOCOL="hydro_remote_agent/configs/evaluate_agent_multi_baseline_v1.json"

cd "${ROOT}"
mkdir -p "${RUN_DIR}"
export TRANSFORMERS_OFFLINE=1
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

evaluate() {
  local predictions="$1"
  local report="$2"
  "${PYTHON}" -u -m hydro_remote_agent.tools.evaluate_agent_routing \
    --gold "${GOLD}" \
    --predictions "${predictions}" \
    --output "${report}" \
    --bootstrap-samples 2000 \
    --bootstrap-seed 20260731
}

"${PYTHON}" -u -m hydro_remote_agent.tools.predict_rule_routing \
  --input "${GOLD}" \
  --output "${RUN_DIR}/rule_router_predictions_240.jsonl" \
  --resume
evaluate "${RUN_DIR}/rule_router_predictions_240.jsonl" "${RUN_DIR}/rule_router_report_240.json"

select_gpu() {
  "${PYTHON}" - <<'PY'
import subprocess

rows = subprocess.check_output(
    ["nvidia-smi", "--query-gpu=index,memory.free,utilization.gpu", "--format=csv,noheader,nounits"],
    text=True,
).splitlines()
candidates = []
for row in rows:
    index, free_mib, utilization = (int(value.strip()) for value in row.split(","))
    if free_mib >= 40000 and utilization <= 20:
        candidates.append((free_mib, -utilization, index))
print(max(candidates)[2] if candidates else "")
PY
}

if [[ -z "${CUDA_VISIBLE_DEVICES:-}" ]]; then
  while true; do
    GPU_ID="$(select_gpu)"
    if [[ -n "${GPU_ID}" ]]; then
      export CUDA_VISIBLE_DEVICES="${GPU_ID}"
      break
    fi
    echo "MULTI_BASELINE_WAITING_FOR_GPU min_free_mib=40000 max_utilization=20"
    sleep 60
  done
fi
echo "MULTI_BASELINE_GPU_SELECTED gpu=${CUDA_VISIBLE_DEVICES}"

"${PYTHON}" -u -m hydro_remote_agent.tools.predict_qwen3_vl_routing \
  --config "${BACKBONE_CONFIG}" \
  --input "${GOLD}" \
  --output "${RUN_DIR}/backbone_minimal_predictions_240.jsonl" \
  --sample-manifest "${RUN_DIR}/backbone_minimal_manifest_240.jsonl" \
  --sample-count 240 \
  --batch-size 8 \
  --max-new-tokens 512 \
  --max-image-pixels 262144 \
  --model-path "${MODEL_PATH}" \
  --image-source-root "${ROOT}/benchmark/10M" \
  --image-cache-root /tmp/vague_hydro_cache/wcs10m \
  --prompt-profile minimal_toolspec \
  --no-resample \
  --resume
evaluate "${RUN_DIR}/backbone_minimal_predictions_240.jsonl" "${RUN_DIR}/backbone_minimal_report_240.json"

"${PYTHON}" -u -m hydro_remote_agent.tools.predict_qwen3_vl_react_routing \
  --config "${BACKBONE_CONFIG}" \
  --input "${GOLD}" \
  --output "${RUN_DIR}/backbone_react_style_predictions_240.jsonl" \
  --batch-size 8 \
  --draft-max-new-tokens 384 \
  --max-new-tokens 512 \
  --max-image-pixels 262144 \
  --model-path "${MODEL_PATH}" \
  --image-source-root "${ROOT}/benchmark/10M" \
  --image-cache-root /tmp/vague_hydro_cache/wcs10m \
  --resume
evaluate "${RUN_DIR}/backbone_react_style_predictions_240.jsonl" "${RUN_DIR}/backbone_react_style_report_240.json"

"${PYTHON}" -u -m hydro_remote_agent.tools.compare_agent_baselines \
  --protocol "${PROTOCOL}" \
  --condition rule_router "${RUN_DIR}/rule_router_predictions_240.jsonl" "${RUN_DIR}/rule_router_report_240.json" \
  --condition backbone_minimal "${RUN_DIR}/backbone_minimal_predictions_240.jsonl" "${RUN_DIR}/backbone_minimal_report_240.json" \
  --condition backbone_full runs/hydro_remote_agent/agent_eval_v1/baseline_predictions_240.jsonl runs/hydro_remote_agent/agent_eval_v1/baseline_routing_report_240.json \
  --condition backbone_react_style "${RUN_DIR}/backbone_react_style_predictions_240.jsonl" "${RUN_DIR}/backbone_react_style_report_240.json" \
  --condition vaguehydro_lora runs/hydro_remote_agent/agent_eval_v1/adapter_predictions_240.jsonl runs/hydro_remote_agent/agent_eval_v1/adapter_routing_report_240.json \
  --output "${RUN_DIR}/comparison_report.json" \
  --markdown "${RUN_DIR}/COMPARISON.md"

echo "AGENT_MULTI_BASELINE_V1_OK run_dir=${RUN_DIR}"
