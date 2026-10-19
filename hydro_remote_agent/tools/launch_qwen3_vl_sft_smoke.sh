#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
PYTHON="python"
RUN_DIR="${ROOT}/runs/hydro_remote_agent/qwen3_vl_8b_lora_smoke"

cd "${ROOT}"
mkdir -p "${RUN_DIR}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export TRANSFORMERS_OFFLINE=1
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

"${PYTHON}" -u -m hydro_remote_agent.tools.train_qwen3_vl_sft \
  --config hydro_remote_agent/configs/train_qwen3_vl_8b_lora.json \
  --max-train-samples 2 \
  --max-eval-samples 1 \
  --max-steps 1 \
  --gradient-accumulation-steps 1 \
  --output-dir "${RUN_DIR}"
