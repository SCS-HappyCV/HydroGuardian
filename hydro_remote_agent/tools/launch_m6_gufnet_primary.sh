#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/workspace/HydroGuardian}"
PYTHON="${PYTHON:-python}"
GPU="${GPU:-2}"
CONFIG="${ROOT}/hydro_remote_agent/configs/train_gufnet_wcs10m_primary_m6.yaml"
RUN_DIR="${ROOT}/runs/hydro_remote_agent/expert_replacement_v1/m6_gufnet_primary/formal"
LAST="${RUN_DIR}/checkpoints/last.ckpt"

mkdir -p "${RUN_DIR}"
cd "${ROOT}"
args=(
  --config "${CONFIG}"
  --output-dir "${RUN_DIR}"
  --seed 20260821
)
if [[ -s "${LAST}" ]]; then
  args+=(--resume "${LAST}")
fi

CUDA_VISIBLE_DEVICES="${GPU}" PYTHONPATH=. \
  "${PYTHON}" -u -m hydro_remote_agent.tools.train_gufnet_primary "${args[@]}"

echo "M6_GUFNET_TRAINING_OK run_dir=${RUN_DIR}"
