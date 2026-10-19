#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
PYTHON="python"
RUN_DIR="${ROOT}/runs/hydro_remote_agent/qwen3_vl_lora_eval"

cd "${ROOT}"
mkdir -p "${RUN_DIR}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-3}"
export TRANSFORMERS_OFFLINE=1
export HF_HUB_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

"${PYTHON}" -u -m hydro_remote_agent.tools.prepare_qwen3_vl_cache \
  --config hydro_remote_agent/configs/prepare_qwen3_vl_cache.json \
  --skip-model

"${PYTHON}" -u -m hydro_remote_agent.tools.predict_qwen3_vl_routing \
  --config hydro_remote_agent/configs/backbone_qwen3_vl_8b.json \
  --input runs/hydro_remote_agent/qwen3_vl_zero_shot/gold_sample_24.jsonl \
  --output "${RUN_DIR}/predictions_24.jsonl" \
  --sample-manifest "${RUN_DIR}/gold_sample_24.jsonl" \
  --sample-count 24 \
  --seed 20260731 \
  --batch-size 2 \
  --max-new-tokens 512 \
  --adapter-path runs/hydro_remote_agent/qwen3_vl_8b_lora_v1 \
  --image-source-root /workspace/HydroGuardian/benchmark/10M \
  --image-cache-root /tmp/vague_hydro_cache/wcs10m \
  --resume

"${PYTHON}" -u -m hydro_remote_agent.tools.evaluate_agent_routing \
  --gold "${RUN_DIR}/gold_sample_24.jsonl" \
  --predictions "${RUN_DIR}/predictions_24.jsonl" \
  --output "${RUN_DIR}/routing_report_24.json"
