from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


AGENT_SERVICE_PORT = int(os.getenv("AGENT_SERVICE_PORT", "8081"))
AGENT_GRPC_PORT = int(os.getenv("AGENT_GRPC_PORT", "9091"))

CASE_SERVICE_NAME = os.getenv("CASE_SERVICE_NAME", "case-service")
FILE_SERVICE_NAME = os.getenv("FILE_SERVICE_NAME", "file-service")
CASE_GRPC_ADDR = os.getenv("CASE_GRPC_ADDR", "")
FILE_GRPC_ADDR = os.getenv("FILE_GRPC_ADDR", "")

HYDRO_PROGRAM3D_SERVICE_NAME = os.getenv("HYDRO_PROGRAM3D_SERVICE_NAME", "hydro-program3d")
HYDRO_PROGRAM3D_URL = os.getenv("HYDRO_PROGRAM3D_URL", "").rstrip("/")
HYDRO_PROGRAM3D_TIMEOUT_SECONDS = float(os.getenv("HYDRO_PROGRAM3D_TIMEOUT_SECONDS", "120"))
HYDRO_PROGRAM3D_CHECKPOINT_NAME = os.getenv(
    "HYDRO_PROGRAM3D_CHECKPOINT_NAME", "hydro_program3d_demo.pth"
)
HYDRO_PROGRAM3D_DEVICE = os.getenv("HYDRO_PROGRAM3D_DEVICE", "cuda")
HYDRO_MODEL_OVERRIDES_JSON = os.getenv("HYDRO_MODEL_OVERRIDES_JSON", "")

CHANGE_DETECTION_SERVICE_NAME = os.getenv("CHANGE_DETECTION_SERVICE_NAME", "change-detection")
CHANGE_DETECTION_URL = os.getenv("CHANGE_DETECTION_URL", "").rstrip("/")
CHANGE_DETECTION_TIMEOUT_SECONDS = float(os.getenv("CHANGE_DETECTION_TIMEOUT_SECONDS", "60"))

SCENE_SAMPLE_DIR = Path(os.getenv("AGENT_SCENE_SAMPLE_DIR", "/app/data/scene_samples"))
ALLOW_DEMO_SCENE_SAMPLE = os.getenv("AGENT_ALLOW_DEMO_SAMPLE", "true").lower() == "true"

NACOS_SERVER_ADDR = os.getenv("NACOS_SERVER_ADDR", "localhost:8848")
NACOS_NAMESPACE = os.getenv("NACOS_NAMESPACE", "public")
NACOS_GROUP = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")
NACOS_CLUSTER = os.getenv("NACOS_CLUSTER", "DEFAULT")
NACOS_SERVICE_NAME = os.getenv("NACOS_SERVICE_NAME", "agent-service")
NACOS_IP = os.getenv("NACOS_IP", "")
NACOS_ENABLED = os.getenv("NACOS_ENABLED", "true").lower() == "true"
NACOS_DISCOVERY_CACHE_TTL_SECONDS = float(os.getenv("NACOS_DISCOVERY_CACHE_TTL_SECONDS", "5"))

LABEL_IDS: dict[str, int] = {
    "cement road": 2,
    "dirt road": 2,
    "road": 2,
    "waterline": 12,
    "ditch": 13,
}


def default_model_overrides() -> dict[str, Any]:
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
            pass
    return overrides
