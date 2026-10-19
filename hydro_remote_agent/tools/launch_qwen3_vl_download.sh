#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/workspace/HydroGuardian"
PYTHON="python"

cd "${PROJECT_ROOT}"
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HUB_DISABLE_XET=1
export HF_HUB_DOWNLOAD_TIMEOUT=600
export PYTHONUNBUFFERED=1

"${PYTHON}" -u -m hydro_remote_agent.tools.download_qwen3_vl_backbone \
  --config hydro_remote_agent/configs/backbone_qwen3_vl_8b.json \
  --max-workers 4
