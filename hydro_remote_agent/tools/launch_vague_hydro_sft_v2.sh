#!/usr/bin/env bash
set -euo pipefail

ROOT="/workspace/HydroGuardian"
PYTHON="python"
OUTPUT_DIR="${ROOT}/hydro_remote_agent/data/vague_hydro_sft_v2"

cd "${ROOT}"
mkdir -p "${OUTPUT_DIR}"
export PYTHONUNBUFFERED=1

"${PYTHON}" -u -m hydro_remote_agent.tools.format_vague_hydro_sft \
  --config hydro_remote_agent/configs/format_vague_hydro_sft_v2.json

