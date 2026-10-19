#!/usr/bin/env bash
set -euo pipefail

ENV_ROOT="/opt/venvs/vague-agent"
RUN_ROOT="/workspace/HydroGuardian/runs/hydro_remote_agent/backbone_setup"
PYPI_MIRROR="https://mirrors.aliyun.com/pypi/simple"

mkdir -p "${RUN_ROOT}"

"${ENV_ROOT}/bin/pip" install \
  --index-url "${PYPI_MIRROR}" \
  --trusted-host mirrors.aliyun.com \
  torch==2.6.0 \
  torchvision==0.21.0 \
  transformers==4.57.6 \
  accelerate==1.12.0 \
  qwen-vl-utils==0.0.14 \
  modelscope==1.39.0 \
  pillow \
  safetensors \
  sentencepiece

"${ENV_ROOT}/bin/python" - <<'PY'
import json
import torch
import transformers
import accelerate

payload = {
    "python": __import__("sys").version.split()[0],
    "torch": torch.__version__,
    "torch_cuda": torch.version.cuda,
    "cuda_available": torch.cuda.is_available(),
    "transformers": transformers.__version__,
    "accelerate": accelerate.__version__,
}
print(json.dumps(payload, sort_keys=True))
PY
