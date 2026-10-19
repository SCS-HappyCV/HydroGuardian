#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/workspace/HydroGuardian}"
PYTHON="${PYTHON:-python}"
RUN_ROOT="${RUN_ROOT:-${ROOT}/runs/hydro_remote_agent/expert_replacement_v1/r007_m5_replay_v1}"
BEFORE_ROOT="${ROOT}/runs/hydro_remote_agent/hydro_agent_bench_gate_v1/task_aware_quality_v1"
AFTER_ROOT="${RUN_ROOT}/task_quality"
FORMAL_ANALYSIS="${RUN_ROOT}/analysis/formal_analysis.json"

while [[ ! -s "${FORMAL_ANALYSIS}" ]]; do
  if ! pgrep -f '[l]aunch_r007_m5_replay_v1.sh' >/dev/null; then
    echo "M5_POSTPROCESS_ABORTED missing=${FORMAL_ANALYSIS}" >&2
    exit 2
  fi
  sleep 30
done

mkdir -p "${RUN_ROOT}/analysis"
cd "${ROOT}"
"${PYTHON}" -u -m hydro_remote_agent.tools.analyze_expert_replacement_stability \
  --before-root "${BEFORE_ROOT}" \
  --after-root "${AFTER_ROOT}" \
  --condition rule_router \
  --condition tool_observation_react \
  --condition glm46v_flash_toolspec \
  --condition deepseek_vl2_small_schema_constrained \
  --condition vaguehydro_lora \
  --condition oracle_gold_routing \
  --expected-count 240 \
  --low-outcome-threshold 0.25 \
  --high-outcome-threshold 0.5 \
  --output "${RUN_ROOT}/analysis/expert_replacement_stability.json" \
  --markdown "${RUN_ROOT}/analysis/EXPERT_REPLACEMENT_STABILITY.md" \
  --transitions-csv "${RUN_ROOT}/analysis/expert_replacement_transitions.csv"

echo "R007_M5_STABILITY_OK root=${RUN_ROOT}"
