#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/workspace/HydroGuardian}"
PYTHON="${PYTHON:-python}"
RUN_ROOT="${RUN_ROOT:-${ROOT}/runs/hydro_remote_agent/expert_replacement_v1/gufnet_m6_replay_v1}"
PTV3_ROOT="${ROOT}/runs/hydro_remote_agent/expert_replacement_v1/r007_m5_replay_v1/task_quality"
GUFNET_ROOT="${RUN_ROOT}/task_quality"
FORMAL_ANALYSIS="${RUN_ROOT}/analysis/formal_analysis.json"

while [[ ! -s "${FORMAL_ANALYSIS}" ]]; do
  if ! pgrep -f '[l]aunch_gufnet_m6_replay_v1.sh' >/dev/null; then
    echo "M6_POSTPROCESS_ABORTED missing=${FORMAL_ANALYSIS}" >&2
    exit 2
  fi
  sleep 30
done

mkdir -p "${RUN_ROOT}/analysis"
cd "${ROOT}"
"${PYTHON}" -u -m hydro_remote_agent.tools.analyze_expert_replacement_stability \
  --before-root "${PTV3_ROOT}" \
  --after-root "${GUFNET_ROOT}" \
  --condition rule_router \
  --condition tool_observation_react \
  --condition glm46v_flash_toolspec \
  --condition deepseek_vl2_small_schema_constrained \
  --condition vaguehydro_lora \
  --condition oracle_gold_routing \
  --expected-count 240 \
  --low-outcome-threshold 0.25 \
  --high-outcome-threshold 0.5 \
  --before-label PTv3 \
  --after-label GUFNet \
  --before-integrity formal_r007_zero_test_overlap \
  --after-integrity formal_gufnet_zero_test_overlap \
  --output "${RUN_ROOT}/analysis/ptv3_to_gufnet_stability.json" \
  --markdown "${RUN_ROOT}/analysis/PTV3_TO_GUFNET_STABILITY.md" \
  --transitions-csv "${RUN_ROOT}/analysis/ptv3_to_gufnet_transitions.csv"

echo "GUFNET_M6_STABILITY_OK root=${RUN_ROOT}"
