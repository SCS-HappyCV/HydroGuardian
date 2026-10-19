#!/usr/bin/env bash
set -euo pipefail

ROOT="${HYDRO_PROJECT_ROOT:-/workspace/HydroGuardian}"
SOURCE_ENV="${HYDRO_SOURCE_ENV:-/opt/venvs/gufnet}"
TARGET_ENV="${HYDRO_DEEPSEEK_ENV:-/opt/venvs/deepseek-vl2-agent}"
SOURCE_REPO="${HYDRO_DEEPSEEK_REPO:-/opt/vendor/DeepSeek-VL2}"
MODEL_PATH="${HYDRO_DEEPSEEK_MODEL:-/models/deepseek-vl2-small}"
MODEL_REVISION="${HYDRO_DEEPSEEK_REVISION:-6033e16432a1d771cf9fe4a6f894ff5e5e1459af}"
SOURCE_REVISION="${HYDRO_DEEPSEEK_SOURCE_REVISION:-ef9f91e2b6426536b83294c11742c27be66361b1}"

if [[ ! -x "${TARGET_ENV}/bin/python" ]]; then
  "${SOURCE_ENV}/bin/python" -m venv --system-site-packages "${TARGET_ENV}"
fi

"${TARGET_ENV}/bin/python" -m pip install -U \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  'transformers==4.38.2' 'tokenizers==0.15.2' 'accelerate>=0.27,<1' \
  'timm==0.9.16' 'einops>=0.7' 'attrdict>=2.0.1' 'sentencepiece>=0.2'
"${TARGET_ENV}/bin/python" -m pip install --no-deps \
  -i https://pypi.tuna.tsinghua.edu.cn/simple 'xformers==0.0.22'
"${TARGET_ENV}/bin/python" -m pip install \
  -i https://pypi.tuna.tsinghua.edu.cn/simple 'lm-format-enforcer==0.10.12'

if [[ ! -d "${SOURCE_REPO}/.git" ]]; then
  mkdir -p "$(dirname "${SOURCE_REPO}")"
  git init "${SOURCE_REPO}"
  git -C "${SOURCE_REPO}" remote add origin https://github.com/deepseek-ai/DeepSeek-VL2.git
fi
if [[ "$(git -C "${SOURCE_REPO}" rev-parse HEAD 2>/dev/null || true)" != "${SOURCE_REVISION}" ]]; then
  git -C "${SOURCE_REPO}" fetch --depth 1 origin "${SOURCE_REVISION}"
  git -C "${SOURCE_REPO}" checkout --detach FETCH_HEAD
fi
"${TARGET_ENV}/bin/python" -m pip install --no-deps -e "${SOURCE_REPO}"

mkdir -p "${MODEL_PATH}"
for attempt in 1 2 3 4 5; do
  if HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}" \
    HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-120}" \
    HF_HUB_ETAG_TIMEOUT="${HF_HUB_ETAG_TIMEOUT:-30}" \
    "${TARGET_ENV}/bin/python" -c \
      'from huggingface_hub import snapshot_download; import sys; snapshot_download(repo_id="deepseek-ai/deepseek-vl2-small", revision=sys.argv[2], local_dir=sys.argv[1])' \
      "${MODEL_PATH}" "${MODEL_REVISION}"; then
    break
  fi
  if (( attempt == 5 )); then
    echo "DEEPSEEK_VL2_DOWNLOAD_FAILED attempts=${attempt}" >&2
    exit 4
  fi
  echo "DEEPSEEK_VL2_DOWNLOAD_RETRY attempt=${attempt}" >&2
  sleep 20
done

cd "${ROOT}"
"${TARGET_ENV}/bin/python" -m hydro_remote_agent.tools.write_external_model_manifest \
  --config hydro_remote_agent/configs/external_deepseek_vl2_small.json \
  --model-path "${MODEL_PATH}"
"${TARGET_ENV}/bin/python" -c \
  'import torch, transformers; from deepseek_vl2.models import DeepseekVLV2Processor; print("DEEPSEEK_VL2_ENV_OK", torch.__version__, transformers.__version__)'
