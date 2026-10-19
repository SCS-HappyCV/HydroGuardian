#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
PYTHON="python"
MODEL_PATH="/models/Qwen3-VL-8B-Instruct"
GOLD="${ROOT}/runs/hydro_remote_agent/agent_eval_v1/gold_240.jsonl"
ADAPTER="${ROOT}/runs/hydro_remote_agent/qwen3_vl_8b_lora_v1"
RUN_ROOT="${ROOT}/runs/hydro_remote_agent/planner_ablations_v1"

cd "${ROOT}"
mkdir -p "${RUN_ROOT}"
export TRANSFORMERS_OFFLINE=1
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

run_profile() {
  local profile="$1"
  local run_dir="${RUN_ROOT}/${profile}"
  mkdir -p "${run_dir}"
  "${PYTHON}" -u -m hydro_remote_agent.tools.predict_qwen3_vl_routing \
    --config hydro_remote_agent/configs/backbone_qwen3_vl_8b.json \
    --input "${GOLD}" \
    --output "${run_dir}/predictions_240.jsonl" \
    --sample-manifest "${run_dir}/gold_240.jsonl" \
    --sample-count 240 \
    --batch-size 8 \
    --max-new-tokens 512 \
    --max-image-pixels 262144 \
    --model-path "${MODEL_PATH}" \
    --adapter-path "${ADAPTER}" \
    --merge-adapter \
    --image-source-root /workspace/HydroGuardian/benchmark/10M \
    --image-cache-root /tmp/vague_hydro_cache/wcs10m \
    --prompt-profile "${profile}" \
    --no-resample \
    --resume
  "${PYTHON}" -u -m hydro_remote_agent.tools.evaluate_agent_routing \
    --gold "${GOLD}" \
    --predictions "${run_dir}/predictions_240.jsonl" \
    --output "${run_dir}/routing_report_240.json" \
    --bootstrap-samples 2000 \
    --bootstrap-seed 20260731
}

for profile in no_tool_descriptions no_request_examples no_workflow_example; do
  echo "PLANNER_ABLATION_START profile=${profile}"
  run_profile "${profile}"
  echo "PLANNER_ABLATION_DONE profile=${profile}"
done

echo "PLANNER_ABLATIONS_OK run_root=${RUN_ROOT}"
