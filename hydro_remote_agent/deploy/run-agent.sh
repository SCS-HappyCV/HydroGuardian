#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${AGENT_STATE_DIR:-/data/agent_state}"
DB_PATH="${AGENT_DB_PATH:-${STATE_DIR}/jobs.sqlite}"
DATABASE_ARG="${DATABASE_URL:-${DB_PATH}}"
EXECUTION_DIR="${AGENT_EXECUTION_DIR:-${STATE_DIR}/executions}"
EXPERT_OUTPUT_DIR="${EXPERT_OUTPUT_DIR:-/data/expert_outputs}"
EXPERT_BASE_URL="${EXPERT_BASE_URL:-http://127.0.0.1:18080}"
REGISTRY="/app/hydro_remote_agent/configs/tool_registry.yaml"
RUN_API="${AGENT_RUN_API:-true}"
RUN_PLANNER="${AGENT_RUN_PLANNER:-false}"
RUN_EXECUTOR="${AGENT_RUN_EXECUTOR:-true}"

mkdir -p "${STATE_DIR}" "${EXECUTION_DIR}" "${EXPERT_OUTPUT_DIR}"

pids=()
shutdown() {
  trap - TERM INT EXIT
  if ((${#pids[@]})); then
    kill "${pids[@]}" 2>/dev/null || true
    wait "${pids[@]}" 2>/dev/null || true
  fi
}
trap shutdown TERM INT EXIT

if [[ "${RUN_API}" == "true" ]]; then
  python -u -m hydro_remote_agent.tools.agent_service_api \
    --db "${DB_PATH}" \
    --database-url "${DATABASE_ARG}" \
    --registry "${REGISTRY}" \
    --allowed-asset-root /data/assets \
    --allowed-asset-root "${EXPERT_OUTPUT_DIR}" \
    --host 0.0.0.0 \
    --port 18080 &
  pids+=("$!")
fi

if [[ "${RUN_PLANNER}" == "true" ]]; then
  python -u -m hydro_remote_agent.tools.agent_service_worker planner \
    --db "${DB_PATH}" \
    --database-url "${DATABASE_ARG}" \
    --registry "${REGISTRY}" \
    --planner-backend "${PLANNER_BACKEND:-qwen}" \
    --model-path "${PLANNER_MODEL_PATH:-/models/planner}" \
    --adapter-path "${PLANNER_ADAPTER_PATH:-/models/planner_adapter}" \
    --max-image-pixels "${PLANNER_MAX_IMAGE_PIXELS:-262144}" \
    --lease-seconds "${PLANNER_LEASE_SECONDS:-1800}" \
    --worker-id planner &
  pids+=("$!")
fi

if [[ "${RUN_EXECUTOR}" == "true" ]]; then
  python -u -m hydro_remote_agent.tools.agent_service_worker executor \
    --db "${DB_PATH}" \
    --database-url "${DATABASE_ARG}" \
    --registry "${REGISTRY}" \
    --expert-work-dir "${EXPERT_OUTPUT_DIR}" \
    --execution-work-dir "${EXECUTION_DIR}" \
    --expert-base-url "${EXPERT_BASE_URL}" \
    --expert-api-prefix /internal \
    --expert-timeout-seconds "${EXPERT_TIMEOUT_SECONDS:-1800}" \
    --lease-seconds "${EXECUTOR_LEASE_SECONDS:-3600}" \
    --max-attempts "${EXECUTOR_MAX_ATTEMPTS:-3}" \
    --transient-retry-delay-seconds "${EXECUTOR_TRANSIENT_RETRY_DELAY_SECONDS:-15}" \
    --worker-id executor &
  pids+=("$!")
fi

if ((${#pids[@]} == 0)); then
  echo "No Agent component is enabled." >&2
  exit 2
fi

wait -n "${pids[@]}"
exit_code=$?
echo "Agent component exited with code ${exit_code}; stopping container." >&2
exit "${exit_code}"
