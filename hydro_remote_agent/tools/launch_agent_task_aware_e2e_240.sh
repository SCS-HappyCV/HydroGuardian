#!/usr/bin/env bash
set -euo pipefail

ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
RUN_ROOT="${RUN_ROOT:-${ROOT}/runs/hydro_remote_agent/agent_task_aware_e2e_240}"
GOLD="${ROOT}/runs/hydro_remote_agent/agent_eval_v1/gold_240.jsonl"
GOLD_SHA256="58c9c016d129c014179cd717739d48ef0e2c0017e1ad37e3374c246b13882b67"
CONDITION="${1:?usage: launch_agent_task_aware_e2e_240.sh tool_observation_react|glm46v_flash_toolspec|deepseek_vl2_small_schema_constrained|vaguehydro_lora|oracle_gold_routing}"
AGENT_SERVICE_URL="${AGENT_SERVICE_URL:-http://127.0.0.1:28080}"
AGENT_ARTIFACT_PROXY_URL="${AGENT_ARTIFACT_PROXY_URL:-http://127.0.0.1:29000}"
SERVICE_IDEMPOTENCY_NAMESPACE="${SERVICE_IDEMPOTENCY_NAMESPACE:-task-aware-240}"
AGENT_PYTHON="${HYDRO_AGENT_PYTHON:-python}"
GLM_PYTHON="${HYDRO_GLM_PYTHON:-/opt/venvs/glm46v-agent/bin/python}"
DEEPSEEK_PYTHON="${HYDRO_DEEPSEEK_PYTHON:-/opt/venvs/deepseek-vl2-agent/bin/python}"

actual_gold_sha256="$(sha256sum "${GOLD}" | awk '{print $1}')"
if [[ "${actual_gold_sha256}" != "${GOLD_SHA256}" ]]; then
  echo "TASK_AWARE_240_GOLD_HASH_MISMATCH expected=${GOLD_SHA256} actual=${actual_gold_sha256}" >&2
  exit 2
fi

mkdir -p "${RUN_ROOT}/${CONDITION}"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"

case "${CONDITION}" in
  vaguehydro_lora)
    exec "${AGENT_PYTHON}" -u -m hydro_remote_agent.tools.merge_recorded_agent_e2e_run \
      --gold "${GOLD}" \
      --expected-gold-sha256 "${GOLD_SHA256}" \
      --predictions "${ROOT}/runs/hydro_remote_agent/agent_eval_v1/adapter_predictions_240.jsonl" \
      --executions "${ROOT}/runs/hydro_remote_agent/agent_execution_eval_v1/execution_results_complete_calibrated_240.jsonl" \
      --condition vaguehydro_lora \
      --output "${RUN_ROOT}/${CONDITION}/run_240.jsonl" \
      --manifest "${RUN_ROOT}/${CONDITION}/merge_manifest.json"
    ;;
  oracle_gold_routing)
    exec "${AGENT_PYTHON}" -u -m hydro_remote_agent.tools.run_oracle_e2e_condition \
      --input "${GOLD}" \
      --expected-input-sha256 "${GOLD_SHA256}" \
      --output "${RUN_ROOT}/${CONDITION}/run_240.jsonl" \
      --agent-service-url "${AGENT_SERVICE_URL}" \
      --agent-artifact-proxy-url "${AGENT_ARTIFACT_PROXY_URL}" \
      --service-idempotency-namespace "${SERVICE_IDEMPOTENCY_NAMESPACE}" \
      --expert-work-dir "${RUN_ROOT}/${CONDITION}/remote_client" \
      --execution-work-dir "${RUN_ROOT}/${CONDITION}/executions" \
      --resume
    ;;
  tool_observation_react)
    PLANNER_GPU="${PLANNER_GPU:?Set PLANNER_GPU after checking nvidia-smi}"
    MIN_FREE_MIB="${MIN_FREE_MIB:-22000}"
    used_mib="$(nvidia-smi --id="${PLANNER_GPU}" --query-gpu=memory.used --format=csv,noheader,nounits)"
    total_mib="$(nvidia-smi --id="${PLANNER_GPU}" --query-gpu=memory.total --format=csv,noheader,nounits)"
    if (( total_mib - used_mib < MIN_FREE_MIB )); then
      echo "TASK_AWARE_240_GPU_PREFLIGHT_FAILED condition=${CONDITION} gpu=${PLANNER_GPU}" >&2
      exit 3
    fi
    export CUDA_VISIBLE_DEVICES="${PLANNER_GPU}"
    exec "${AGENT_PYTHON}" -u -m hydro_remote_agent.tools.run_agent_e2e_condition \
      --condition tool_observation_react \
      --config "${ROOT}/hydro_remote_agent/configs/backbone_qwen3_vl_8b.json" \
      --input "${GOLD}" \
      --output "${RUN_ROOT}/${CONDITION}/run_240.jsonl" \
      --agent-service-url "${AGENT_SERVICE_URL}" \
      --agent-artifact-proxy-url "${AGENT_ARTIFACT_PROXY_URL}" \
      --service-idempotency-namespace "${SERVICE_IDEMPOTENCY_NAMESPACE}" \
      --expert-work-dir "${RUN_ROOT}/${CONDITION}/remote_client" \
      --execution-work-dir "${RUN_ROOT}/${CONDITION}/executions" \
      --max-new-tokens 512 \
      --max-image-pixels 262144 \
      --resume
    ;;
  glm46v_flash_toolspec)
    PLANNER_GPU="${PLANNER_GPU:?Set PLANNER_GPU after checking nvidia-smi}"
    MIN_FREE_MIB="${MIN_FREE_MIB:-36000}"
    used_mib="$(nvidia-smi --id="${PLANNER_GPU}" --query-gpu=memory.used --format=csv,noheader,nounits)"
    total_mib="$(nvidia-smi --id="${PLANNER_GPU}" --query-gpu=memory.total --format=csv,noheader,nounits)"
    if (( total_mib - used_mib < MIN_FREE_MIB )); then
      echo "TASK_AWARE_240_GPU_PREFLIGHT_FAILED condition=${CONDITION} gpu=${PLANNER_GPU}" >&2
      exit 3
    fi
    export CUDA_VISIBLE_DEVICES="${PLANNER_GPU}"
    exec "${GLM_PYTHON}" -u -m hydro_remote_agent.tools.run_external_vlm_e2e_condition \
      --config "${ROOT}/hydro_remote_agent/configs/external_glm46v_flash.json" \
      --input "${GOLD}" \
      --output "${RUN_ROOT}/${CONDITION}/run_240.jsonl" \
      --agent-service-url "${AGENT_SERVICE_URL}" \
      --agent-artifact-proxy-url "${AGENT_ARTIFACT_PROXY_URL}" \
      --service-idempotency-namespace "${SERVICE_IDEMPOTENCY_NAMESPACE}" \
      --expert-work-dir "${RUN_ROOT}/${CONDITION}/remote_client" \
      --execution-work-dir "${RUN_ROOT}/${CONDITION}/executions" \
      --max-new-tokens 1024 \
      --max-image-pixels 262144 \
      --resume
    ;;
  deepseek_vl2_small_schema_constrained)
    PLANNER_GPU="${PLANNER_GPU:?Set PLANNER_GPU after checking nvidia-smi}"
    MIN_FREE_MIB="${MIN_FREE_MIB:-45000}"
    used_mib="$(nvidia-smi --id="${PLANNER_GPU}" --query-gpu=memory.used --format=csv,noheader,nounits)"
    total_mib="$(nvidia-smi --id="${PLANNER_GPU}" --query-gpu=memory.total --format=csv,noheader,nounits)"
    if (( total_mib - used_mib < MIN_FREE_MIB )); then
      echo "TASK_AWARE_240_GPU_PREFLIGHT_FAILED condition=${CONDITION} gpu=${PLANNER_GPU}" >&2
      exit 3
    fi
    export CUDA_VISIBLE_DEVICES="${PLANNER_GPU}"
    exec "${DEEPSEEK_PYTHON}" -u -m hydro_remote_agent.tools.run_external_vlm_e2e_condition \
      --config "${ROOT}/hydro_remote_agent/configs/external_deepseek_vl2_small_schema_constrained_240.json" \
      --input "${GOLD}" \
      --output "${RUN_ROOT}/${CONDITION}/run_240.jsonl" \
      --agent-service-url "${AGENT_SERVICE_URL}" \
      --agent-artifact-proxy-url "${AGENT_ARTIFACT_PROXY_URL}" \
      --service-idempotency-namespace "${SERVICE_IDEMPOTENCY_NAMESPACE}" \
      --expert-work-dir "${RUN_ROOT}/${CONDITION}/remote_client" \
      --execution-work-dir "${RUN_ROOT}/${CONDITION}/executions" \
      --max-new-tokens 512 \
      --max-image-pixels 262144 \
      --resume
    ;;
  *)
    echo "Unknown condition: ${CONDITION}" >&2
    exit 64
    ;;
esac
