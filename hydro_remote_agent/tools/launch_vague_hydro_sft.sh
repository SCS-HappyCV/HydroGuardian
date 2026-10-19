#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/workspace/HydroGuardian"
PYTHON="python"
OUTPUT_DIR="hydro_remote_agent/data/vague_hydro_sft"

cd "${PROJECT_ROOT}"
mkdir -p "${OUTPUT_DIR}"
export PYTHONUNBUFFERED=1

"${PYTHON}" -u -m hydro_remote_agent.tools.format_vague_hydro_sft \
  --config hydro_remote_agent/configs/format_vague_hydro_sft.json \
  2>&1 | tee "${OUTPUT_DIR}/format.log"
