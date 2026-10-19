#!/usr/bin/env bash
set -euo pipefail

ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
PYTHON="${HYDRO_AGENT_PYTHON:-python}"
EXPERT_URL="${EXPERT_URL:-http://127.0.0.1:19091}"
RUN_DIR="${RUN_DIR:-${ROOT}/runs/hydro_remote_agent/oracle_gold_routing_v1/oracle_gold_routing}"
GOLD="${ROOT}/runs/hydro_remote_agent/agent_e2e_comparison_v1/gold_50.jsonl"
GOLD_SHA256="23a29fdba37029992b641561244bc7b3d7ca590217ab0cba06ba437963696463"

mkdir -p "${RUN_DIR}"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"

exec "${PYTHON}" -u -m hydro_remote_agent.tools.run_oracle_e2e_condition \
  --input "${GOLD}" \
  --expected-input-sha256 "${GOLD_SHA256}" \
  --output "${RUN_DIR}/run_50.jsonl" \
  --expert-base-url "${EXPERT_URL}" \
  --expert-work-dir "${RUN_DIR}/remote_client" \
  --execution-work-dir "${RUN_DIR}/executions" \
  --resume
