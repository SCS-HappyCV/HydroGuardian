#!/usr/bin/env bash
set -euo pipefail

ROOT=/workspace/HydroGuardian
REPORTS="${ROOT}/runs/hydro_remote_agent/vaguehydro_legality_repair_pilot_v3"
OUTPUT="${REPORTS}/CHANGE_ARTIFACT_ARCHIVE"

cd "${ROOT}"
python hydro_remote_agent/tools/archive_change_artifacts.py \
  --reports-dir "${REPORTS}" \
  --output-dir "${OUTPUT}" \
  --asset-base-url http://127.0.0.1:29000 \
  --include-report REAL_CHANGE_CANARY_20261006_R01_C01_retry.json \
  --include-report REAL_CHANGE_BATCH_20261006_batch01_rest.json \
  --include-report REAL_CHANGE_BATCH_20261006_batch02.json \
  --include-report REAL_CHANGE_BATCH_20261006_batch03.json \
  --include-report REAL_CHANGE_BATCH_20261006_batch04.json \
  --timeout 600 \
  2>&1 | tee "${REPORTS}/CHANGE_ARTIFACT_ARCHIVE.log"
