#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/workspace/HydroGuardian"
PYTHON="python"
OUTPUT_DIR="hydro_remote_agent/data/vague_hydro_generated"

cd "${PROJECT_ROOT}"
mkdir -p "${OUTPUT_DIR}"
export PYTHONUNBUFFERED=1
ulimit -n 65536

"${PYTHON}" -u -m hydro_remote_agent.tools.generate_vague_queries \
  --config hydro_remote_agent/configs/generate_vague_hydro_qwen35_flash_batch_chat.json \
  --batch-size 1 \
  --workers 32 \
  --output-dir "${OUTPUT_DIR}" 2>&1 | tee -a "${OUTPUT_DIR}/finalize.log"
