#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
PYTHON="python"
RUN_DIR="${ROOT}/runs/hydro_remote_agent/qwen3_vl_8b_lora_v1"

cd "${ROOT}"
mkdir -p "${RUN_DIR}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-1}"
export TRANSFORMERS_OFFLINE=1
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

"${PYTHON}" -u -m hydro_remote_agent.tools.prepare_qwen3_vl_cache \
  --config hydro_remote_agent/configs/prepare_qwen3_vl_cache.json \
  --skip-model

"${PYTHON}" -u -m hydro_remote_agent.tools.train_qwen3_vl_sft \
  --config hydro_remote_agent/configs/train_qwen3_vl_8b_lora.json \
  --resume-from-checkpoint latest

