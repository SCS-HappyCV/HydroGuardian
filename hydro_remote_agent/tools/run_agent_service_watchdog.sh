#!/usr/bin/env bash
set -uo pipefail

ROOT="/workspace/HydroGuardian"
COMPONENT="${1:?usage: run_agent_service_watchdog.sh api|planner|executor}"
RUN_DIR="${ROOT}/runs/hydro_remote_agent/agent_service_v1"
RESTART_DELAY_SECONDS="${RESTART_DELAY_SECONDS:-2}"
LOG_PATH="${RUN_DIR}/${COMPONENT}.log"

mkdir -p "${RUN_DIR}"
cd "${ROOT}"

while true; do
  echo "${COMPONENT^^}_WATCHDOG_START at=$(date -Is)" >> "${LOG_PATH}"
  GPU_ID="${GPU_ID:-0}" LEASE_SECONDS="${LEASE_SECONDS:-120}" \
    bash hydro_remote_agent/tools/launch_agent_service_component.sh "${COMPONENT}" \
    >> "${LOG_PATH}" 2>&1
  exit_code=$?
  echo "${COMPONENT^^}_WATCHDOG_EXIT code=${exit_code} at=$(date -Is)" >> "${LOG_PATH}"
  sleep "${RESTART_DELAY_SECONDS}"
done
