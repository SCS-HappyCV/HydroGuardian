#!/usr/bin/env bash
set -euo pipefail

ROOT=/workspace/HydroGuardian
DATA="${ROOT}/hydro_remote_agent/canary_change/DTXX"
OUT="runs/hydro_remote_agent/vaguehydro_legality_repair_pilot_v3"

cd "${ROOT}"
python hydro_remote_agent/tools/run_change_batch.py \
  --run-id 20261006_batch03 \
  --output "${OUT}/REAL_CHANGE_BATCH_20261006_batch03.json" \
  --pair R03_C01 "${DATA}/before/R03_C01.tif" "${DATA}/after/R03_C01.tif" \
  --pair R03_C02 "${DATA}/before/R03_C02.tif" "${DATA}/after/R03_C02.tif" \
  --pair R03_C03 "${DATA}/before/R03_C03.tif" "${DATA}/after/R03_C03.tif" \
  --pair R03_C04 "${DATA}/before/R03_C04.tif" "${DATA}/after/R03_C04.tif" \
  2>&1 | tee "${OUT}/REAL_CHANGE_BATCH_20261006_batch03.log"
