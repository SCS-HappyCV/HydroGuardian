#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
PYTHON="python"
RUN_DIR="${ROOT}/runs/hydro_remote_agent/qwen3_vl_zero_shot"

cd "${ROOT}"
mkdir -p "${RUN_DIR}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export TRANSFORMERS_OFFLINE=1
export HF_HUB_OFFLINE=1

"${PYTHON}" -u -m hydro_remote_agent.tools.predict_qwen3_vl_routing \
  --config hydro_remote_agent/configs/backbone_qwen3_vl_8b.json \
  --input hydro_remote_agent/data/vague_hydro_sft/test_sft.jsonl \
  --output "${RUN_DIR}/predictions_24.jsonl" \
  --sample-manifest "${RUN_DIR}/gold_sample_24.jsonl" \
  --sample-count 24 \
  --seed 20260731 \
  --batch-size 2 \
  --max-new-tokens 512 \
  --resume

"${PYTHON}" -u -m hydro_remote_agent.tools.evaluate_agent_routing \
  --gold "${RUN_DIR}/gold_sample_24.jsonl" \
  --predictions "${RUN_DIR}/predictions_24.jsonl" \
  --output "${RUN_DIR}/routing_report_24.json"

