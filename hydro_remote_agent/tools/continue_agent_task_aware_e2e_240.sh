#!/usr/bin/env bash
set -euo pipefail

ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
RUN_ROOT="${RUN_ROOT:-${ROOT}/runs/hydro_remote_agent/agent_task_aware_e2e_240}"
SPLIT_ROOT="${SPLIT_ROOT:-/data/wcs10m/splits/wcs10m_primary}"
POLL_SECONDS="${POLL_SECONDS:-60}"
GLM_MIN_FREE_MIB="${GLM_MIN_FREE_MIB:-32000}"
GLM_MAX_UTIL="${GLM_MAX_UTIL:-25}"
STABLE_POLLS="${STABLE_POLLS:-3}"

count_rows() {
  local path="$1"
  if [[ -f "${path}" ]]; then
    wc -l < "${path}"
  else
    echo 0
  fi
}

condition_path() {
  echo "${RUN_ROOT}/$1/run_240.jsonl"
}

wait_for_glm_gpu() {
  local last_candidate=""
  local stable_count=0
  while true; do
    local best_gpu=""
    local best_free=-1
    while IFS=',' read -r raw_index raw_free raw_util; do
      local index free util
      index="$(echo "${raw_index}" | xargs)"
      free="$(echo "${raw_free}" | xargs)"
      util="$(echo "${raw_util}" | xargs)"
      if (( free >= GLM_MIN_FREE_MIB && util <= GLM_MAX_UTIL && free > best_free )); then
        best_gpu="${index}"
        best_free="${free}"
      fi
    done < <(
      nvidia-smi \
        --query-gpu=index,memory.free,utilization.gpu \
        --format=csv,noheader,nounits
    )

    if [[ -n "${best_gpu}" && "${best_gpu}" == "${last_candidate}" ]]; then
      stable_count=$((stable_count + 1))
    elif [[ -n "${best_gpu}" ]]; then
      last_candidate="${best_gpu}"
      stable_count=1
    else
      last_candidate=""
      stable_count=0
    fi
    echo "TASK_AWARE_240_GPU_WAIT candidate=${best_gpu:-none} free_mib=${best_free} stable=${stable_count}/${STABLE_POLLS}"
    if [[ -n "${best_gpu}" && ${stable_count} -ge ${STABLE_POLLS} ]]; then
      echo "${best_gpu}"
      return 0
    fi
    sleep "${POLL_SECONDS}"
  done
}

mkdir -p "${RUN_ROOT}"
cd "${ROOT}"

glm_path="$(condition_path glm46v_flash_toolspec)"
if [[ "$(count_rows "${glm_path}")" -lt 240 ]]; then
  glm_gpu="$(wait_for_glm_gpu | tee -a "${RUN_ROOT}/continuation_gpu_wait.log" | tail -1)"
  echo "TASK_AWARE_240_GLM_START gpu=${glm_gpu}"
  PLANNER_GPU="${glm_gpu}" MIN_FREE_MIB="${GLM_MIN_FREE_MIB}" \
    SERVICE_IDEMPOTENCY_NAMESPACE="task-aware-240-glm-uniform-20260815" \
    bash hydro_remote_agent/tools/launch_agent_task_aware_e2e_240.sh glm46v_flash_toolspec
fi

react_path="$(condition_path tool_observation_react)"
while [[ "$(count_rows "${react_path}")" -lt 240 ]]; do
  react_pid_file="${RUN_ROOT}/tool_observation_react/formal.pid"
  if [[ ! -f "${react_pid_file}" ]] || ! kill -0 "$(cat "${react_pid_file}")" 2>/dev/null; then
    echo "TASK_AWARE_240_REACT_STOPPED rows=$(count_rows "${react_path}")" >&2
    exit 4
  fi
  echo "TASK_AWARE_240_REACT_WAIT rows=$(count_rows "${react_path}")/240"
  sleep "${POLL_SECONDS}"
done

deepseek_path="$(condition_path deepseek_vl2_small_schema_constrained)"
while [[ "$(count_rows "${deepseek_path}")" -lt 240 ]]; do
  deepseek_pid_file="${RUN_ROOT}/deepseek_vl2_small_schema_constrained/formal.pid"
  if [[ ! -f "${deepseek_pid_file}" ]] || ! kill -0 "$(cat "${deepseek_pid_file}")" 2>/dev/null; then
    echo "TASK_AWARE_240_DEEPSEEK_STOPPED rows=$(count_rows "${deepseek_path}")" >&2
    exit 4
  fi
  echo "TASK_AWARE_240_DEEPSEEK_WAIT rows=$(count_rows "${deepseek_path}")/240"
  sleep "${POLL_SECONDS}"
done

for condition in vaguehydro_lora oracle_gold_routing tool_observation_react glm46v_flash_toolspec deepseek_vl2_small_schema_constrained; do
  rows="$(count_rows "$(condition_path "${condition}")")"
  if [[ "${rows}" -ne 240 ]]; then
    echo "TASK_AWARE_240_INCOMPLETE condition=${condition} rows=${rows}" >&2
    exit 5
  fi
done

bash hydro_remote_agent/tools/analyze_agent_task_aware_e2e_240.sh

python \
  -m hydro_remote_agent.tools.collect_experiment_results \
  --project-root "${ROOT}" \
  --output-dir "${ROOT}/runs/hydro_remote_agent/experiments_v1"

python \
  -m hydro_remote_agent.tools.audit_experiment_integrity \
  --project-root "${ROOT}" \
  --split-root "${SPLIT_ROOT}" \
  --output-dir "${RUN_ROOT}/integrity_audit"

echo "AGENT_TASK_AWARE_E2E_240_CONTINUATION_OK root=${RUN_ROOT}"
