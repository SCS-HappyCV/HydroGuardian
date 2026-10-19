from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServiceSettings:
    service_root: Path
    output_dir: Path
    weights_path: Path
    host: str = "0.0.0.0"
    port: int = 8011
    device: str = "cuda"
    nacos_enabled: bool = True
    nacos_server_addr: str = "localhost:8848"
    nacos_namespace: str = "public"
    nacos_group: str = "DEFAULT_GROUP"
    nacos_cluster: str = "DEFAULT"
    nacos_service_name: str = "change-detection"
    nacos_ip: str = ""
    nacos_heartbeat_interval_seconds: float = 5.0


def load_settings() -> ServiceSettings:
    service_root = Path(__file__).resolve().parent
    output_dir = service_root / "outputs"
    weights_path = service_root / "weight" / "best_model.pth"
    return ServiceSettings(
        service_root=service_root,
        output_dir=Path(os.getenv("RFANET_OUTPUT_DIR", str(output_dir))),
        weights_path=Path(os.getenv("RFANET_WEIGHTS", str(weights_path))),
        host=os.getenv("CHANGE_DETECTION_HOST", "0.0.0.0"),
        port=int(os.getenv("CHANGE_DETECTION_PORT", "8011")),
        device=os.getenv("RFANET_DEVICE", "cuda"),
        nacos_enabled=os.getenv("NACOS_ENABLED", "true").lower() == "true",
        nacos_server_addr=os.getenv("NACOS_SERVER_ADDR", "localhost:8848"),
        nacos_namespace=os.getenv("NACOS_NAMESPACE", "public"),
        nacos_group=os.getenv("NACOS_GROUP", "DEFAULT_GROUP"),
        nacos_cluster=os.getenv("NACOS_CLUSTER", "DEFAULT"),
        nacos_service_name=os.getenv("NACOS_SERVICE_NAME", "change-detection"),
        nacos_ip=os.getenv("NACOS_IP", ""),
        nacos_heartbeat_interval_seconds=float(os.getenv("NACOS_HEARTBEAT_INTERVAL_SECONDS", "5")),
    )
