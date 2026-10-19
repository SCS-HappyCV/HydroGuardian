#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/workspace/HydroGuardian"
PYTHON="python"
OUTPUT_DIR="hydro_remote_agent/data/vague_hydro_generated_pilot"

cd "${PROJECT_ROOT}"
mkdir -p "${OUTPUT_DIR}"
export PYTHONUNBUFFERED=1

"${PYTHON}" -u -m hydro_remote_agent.tools.generate_vague_queries \
  --config hydro_remote_agent/configs/generate_vague_hydro_qwen35_flash.json \
  --limit-per-split 2 \
  --batch-size 2 \
  --workers 2 \
  --output-dir "${OUTPUT_DIR}" 2>&1 | tee "${OUTPUT_DIR}/generation.log"
