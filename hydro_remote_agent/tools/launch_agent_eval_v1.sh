#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
PYTHON="python"
RUN_DIR="${ROOT}/runs/hydro_remote_agent/agent_eval_v1"
GOLD="${RUN_DIR}/gold_240.jsonl"
MODEL_PATH="/models/Qwen3-VL-8B-Instruct"

cd "${ROOT}"
mkdir -p "${RUN_DIR}"
export TRANSFORMERS_OFFLINE=1
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

"${PYTHON}" -u -m hydro_remote_agent.tools.prepare_qwen3_vl_cache \
  --config hydro_remote_agent/configs/prepare_qwen3_vl_cache.json \
  --skip-model

select_gpu() {
  "${PYTHON}" - <<'PY'
import subprocess

rows = subprocess.check_output(
    [
        "nvidia-smi",
        "--query-gpu=index,memory.free,utilization.gpu",
        "--format=csv,noheader,nounits",
    ],
    text=True,
).splitlines()
candidates = []
for row in rows:
    index, free_mib, utilization = (int(value.strip()) for value in row.split(","))
    if free_mib >= 45000 and utilization <= 20:
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
    echo "AGENT_EVAL_WAITING_FOR_GPU min_free_mib=45000 max_utilization=20"
    sleep 60
  done
fi
echo "AGENT_EVAL_GPU_SELECTED gpu=${CUDA_VISIBLE_DEVICES}"

run_prediction() {
  local output="$1"
  shift
  "${PYTHON}" -u -m hydro_remote_agent.tools.predict_qwen3_vl_routing \
    --config hydro_remote_agent/configs/backbone_qwen3_vl_8b.json \
    --input "${GOLD}" \
    --output "${output}" \
    --sample-manifest "${GOLD}" \
    --sample-count 240 \
    --batch-size 8 \
    --max-new-tokens 512 \
    --max-image-pixels 262144 \
    --model-path "${MODEL_PATH}" \
    --image-source-root /workspace/HydroGuardian/benchmark/10M \
    --image-cache-root /tmp/vague_hydro_cache/wcs10m \
    --no-resample \
    --resume \
    "$@"
}

run_evaluation() {
  local predictions="$1"
  local report="$2"
  "${PYTHON}" -u -m hydro_remote_agent.tools.evaluate_agent_routing \
    --gold "${GOLD}" \
    --predictions "${predictions}" \
    --output "${report}" \
    --bootstrap-samples 2000 \
    --bootstrap-seed 20260731
}

run_prediction "${RUN_DIR}/adapter_predictions_240.jsonl" \
  --adapter-path runs/hydro_remote_agent/qwen3_vl_8b_lora_v1 \
  --merge-adapter
run_evaluation \
  "${RUN_DIR}/adapter_predictions_240.jsonl" \
  "${RUN_DIR}/adapter_routing_report_240.json"

run_prediction "${RUN_DIR}/baseline_predictions_240.jsonl"
run_evaluation \
  "${RUN_DIR}/baseline_predictions_240.jsonl" \
  "${RUN_DIR}/baseline_routing_report_240.json"

echo "AGENT_EVAL_V1_OK run_dir=${RUN_DIR}"
