#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/workspace/HydroGuardian"
PYTHON="python"
OUTPUT_DIR="hydro_remote_agent/data/vague_hydro_generated"
LOG_PATH="${OUTPUT_DIR}/generation.log"
CONFIG="hydro_remote_agent/configs/generate_vague_hydro_qwen35_flash_batch_chat.json"

cd "${PROJECT_ROOT}"
mkdir -p "${OUTPUT_DIR}"
export PYTHONUNBUFFERED=1
ulimit -n 65536

MAX_PASSES=8
for pass_index in $(seq 1 "${MAX_PASSES}"); do
  batch_size=2
  if (( pass_index > 1 )); then
    batch_size=1
  fi

  printf '\n[%s] Starting full VagueHydro Batch Chat generation pass=%d/%d batch_size=%d\n' \
    "$(date --iso-8601=seconds)" "${pass_index}" "${MAX_PASSES}" "${batch_size}" \
    | tee -a "${LOG_PATH}"

  set +e
  "${PYTHON}" -u -m hydro_remote_agent.tools.generate_vague_queries \
    --config "${CONFIG}" \
    --batch-size "${batch_size}" \
    --output-dir "${OUTPUT_DIR}" 2>&1 | tee -a "${LOG_PATH}"
  status=${PIPESTATUS[0]}
  set -e

  if (( status == 0 )); then
    printf '[%s] Full VagueHydro generation completed pass=%d\n' \
      "$(date --iso-8601=seconds)" "${pass_index}" | tee -a "${LOG_PATH}"
    exit 0
  fi

  printf '[%s] Pass %d failed; cached successes retained, retrying uncached tasks\n' \
    "$(date --iso-8601=seconds)" "${pass_index}" | tee -a "${LOG_PATH}"
  sleep 30
done

printf '[%s] Full generation still has failures after %d passes\n' \
  "$(date --iso-8601=seconds)" "${MAX_PASSES}" | tee -a "${LOG_PATH}"
exit 1
