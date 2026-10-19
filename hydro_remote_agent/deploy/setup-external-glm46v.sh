#!/usr/bin/env bash
set -euo pipefail

ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
SOURCE_ENV="${HYDRO_SOURCE_ENV:-/opt/venvs/vague-agent}"
TARGET_ENV="${HYDRO_GLM_ENV:-/opt/venvs/glm46v-agent}"

if [[ ! -x "${TARGET_ENV}/bin/python" ]]; then
  "${SOURCE_ENV}/bin/python" -m venv --system-site-packages "${TARGET_ENV}"
fi

"${TARGET_ENV}/bin/python" -m pip install \
  -U \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  'transformers==5.14.1'

cd "${ROOT}"
"${SOURCE_ENV}/bin/python" -m hydro_remote_agent.tools.download_modelscope_snapshot \
  --config hydro_remote_agent/configs/external_glm46v_flash.json

"${TARGET_ENV}/bin/python" -c \
  'import torch, transformers; from transformers import Glm4vForConditionalGeneration; print("GLM_ENV_OK", torch.__version__, transformers.__version__)'
