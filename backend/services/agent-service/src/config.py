from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def first_non_empty_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


# 这份文件集中管理 agent-service 的运行配置。
# 接手时如果怀疑“为什么连到这个服务 / 为什么读这个目录 / 为什么用这个模型配置”，
# 通常先看这里。
AGENT_SERVICE_PORT = int(os.getenv("AGENT_SERVICE_PORT", "8081"))
AGENT_GRPC_PORT = int(os.getenv("AGENT_GRPC_PORT", "9091"))

CASE_SERVICE_NAME = os.getenv("CASE_SERVICE_NAME", "case-service")
FILE_SERVICE_NAME = os.getenv("FILE_SERVICE_NAME", "file-service")
CASE_GRPC_ADDR = os.getenv("CASE_GRPC_ADDR", "")
FILE_GRPC_ADDR = os.getenv("FILE_GRPC_ADDR", "")
FILE_GRPC_MAX_MESSAGE_BYTES = int(os.getenv("FILE_GRPC_MAX_MESSAGE_BYTES", "104857600"))
FILE_GRPC_TIMEOUT_SECONDS = float(os.getenv("FILE_GRPC_TIMEOUT_SECONDS", "30"))

HYDRO_PROGRAM3D_SERVICE_NAME = os.getenv("HYDRO_PROGRAM3D_SERVICE_NAME", "hydro-program3d")
HYDRO_PROGRAM3D_URL = os.getenv("HYDRO_PROGRAM3D_URL", "").rstrip("/")
HYDRO_PROGRAM3D_TIMEOUT_SECONDS = float(os.getenv("HYDRO_PROGRAM3D_TIMEOUT_SECONDS", "120"))
HYDRO_PROGRAM3D_CHECKPOINT_NAME = os.getenv(
    "HYDRO_PROGRAM3D_CHECKPOINT_NAME", "hydro_program3d_demo.pth"
)
HYDRO_PROGRAM3D_DEVICE = os.getenv("HYDRO_PROGRAM3D_DEVICE", "cuda")
HYDRO_MODEL_OVERRIDES_JSON = os.getenv("HYDRO_MODEL_OVERRIDES_JSON", "")

TASK_PARSER_BACKEND = os.getenv("AGENT_TASK_PARSER_BACKEND", "auto").lower()
TASK_PARSER_OPENAI_MODEL = os.getenv("AGENT_TASK_PARSER_MODEL", "gpt-5.5")
TASK_PARSER_OPENAI_TIMEOUT_SECONDS = float(os.getenv("AGENT_TASK_PARSER_TIMEOUT_SECONDS", "45"))
TASK_PARSER_OPENAI_MAX_TOKENS = int(os.getenv("AGENT_TASK_PARSER_MAX_TOKENS", "500"))
TASK_PARSER_OPENAI_DISABLE_THINKING = (
    os.getenv("AGENT_TASK_PARSER_DISABLE_THINKING", "false").lower() == "true"
)
TASK_PARSER_FALLBACK_TO_RULE = os.getenv("AGENT_TASK_PARSER_FALLBACK_TO_RULE", "true").lower() == "true"
TASK_PARSER_OPENAI_BASE_URL = first_non_empty_env(
    "AGENT_TASK_PARSER_OPENAI_BASE_URL",
    "OPENAI_BASE_URL",
)
TASK_PARSER_OPENAI_API_KEY = first_non_empty_env(
    "AGENT_TASK_PARSER_OPENAI_API_KEY",
    "OPENAI_API_KEY",
    "DASHSCOPE_API_KEY",
)
TASK_PARSER_OPENAI_ORGANIZATION = first_non_empty_env(
    "AGENT_TASK_PARSER_OPENAI_ORG_ID",
    "OPENAI_ORG_ID",
)
TASK_PARSER_OPENAI_PROJECT = first_non_empty_env(
    "AGENT_TASK_PARSER_OPENAI_PROJECT_ID",
    "OPENAI_PROJECT_ID",
)

CHANGE_DETECTION_SERVICE_NAME = os.getenv("CHANGE_DETECTION_SERVICE_NAME", "change-detection")
CHANGE_DETECTION_URL = os.getenv("CHANGE_DETECTION_URL", "").rstrip("/")
CHANGE_DETECTION_TIMEOUT_SECONDS = float(os.getenv("CHANGE_DETECTION_TIMEOUT_SECONDS", "60"))

SCENE_SAMPLE_DIR = Path(os.getenv("AGENT_SCENE_SAMPLE_DIR", "/app/data/scene_samples"))
SCENE_MANIFEST_DIR = Path(os.getenv("AGENT_SCENE_MANIFEST_DIR", "/app/data/scene_manifests"))
ALLOW_DEMO_SCENE_SAMPLE = os.getenv("AGENT_ALLOW_DEMO_SAMPLE", "true").lower() == "true"

NACOS_SERVER_ADDR = os.getenv("NACOS_SERVER_ADDR", "localhost:8848")
NACOS_NAMESPACE = os.getenv("NACOS_NAMESPACE", "public")
NACOS_GROUP = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")
NACOS_CLUSTER = os.getenv("NACOS_CLUSTER", "DEFAULT")
NACOS_SERVICE_NAME = os.getenv("NACOS_SERVICE_NAME", "agent-service")
NACOS_IP = os.getenv("NACOS_IP", "")
NACOS_ENABLED = os.getenv("NACOS_ENABLED", "true").lower() == "true"
NACOS_DISCOVERY_CACHE_TTL_SECONDS = float(os.getenv("NACOS_DISCOVERY_CACHE_TTL_SECONDS", "5"))

# 这里是任务解析阶段用到的最小 label id 映射。
# 如果后面 program 覆盖更多类别，通常需要先补这里。
LABEL_IDS: dict[str, int] = {
    "shed": 0,
    "concrete house": 1,
    "cement road": 2,
    "dirt road": 3,
    "road": 2,
    "slope": 4,
    "steep_slope": 4,
    "scarp": 5,
    "dam": 6,
    "vegetable field": 7,
    "grassland": 8,
    "dryland": 9,
    "woodland": 10,
    "bareland": 11,
    "waterline": 12,
    "ditch": 13,
    "others": 14,
}


def default_model_overrides() -> dict[str, Any]:
    # 这是调用 hydro-program3d /execute 时默认附带的模型参数。
    # 如果部署环境需要临时覆盖，可以通过 HYDRO_MODEL_OVERRIDES_JSON 注入。
    overrides: dict[str, Any] = {
        "point_encoder_type": "spconv",
        "text_encoder_type": "clip",
        "clip_model_name": "ViT-B-32",
        "use_ortho_prior": True,
        "use_program_executor": True,
        "program_schema_mode": "field",
        "program_version": "v1_field",
    }
    if HYDRO_MODEL_OVERRIDES_JSON:
        try:
            custom = json.loads(HYDRO_MODEL_OVERRIDES_JSON)
            if isinstance(custom, dict):
                overrides.update(custom)
        except json.JSONDecodeError:
            # 这里静默忽略非法 JSON，是为了避免联调时因为一个临时环境变量
            # 直接把整个服务启动或调用打挂。
            pass
    return overrides
