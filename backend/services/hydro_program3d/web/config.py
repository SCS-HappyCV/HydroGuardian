from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServiceSettings:
    service_root: Path
    algorithm_dir: Path
    data_dir: Path
    checkpoint_dir: Path
    host: str = "0.0.0.0"
    port: int = 8093
    nacos_enabled: bool = True
    nacos_server_addr: str = "localhost:8848"
    nacos_namespace: str = "public"
    nacos_group: str = "DEFAULT_GROUP"
    nacos_cluster: str = "DEFAULT"
    nacos_service_name: str = "hydro-program3d"
    nacos_ip: str = ""
    nacos_heartbeat_interval_seconds: float = 5.0


def load_settings() -> ServiceSettings:
    service_root = Path(__file__).resolve().parents[1]
    algorithm_dir = service_root / "algorithm"
    data_dir = service_root / "data"
    checkpoint_dir = service_root / "checkpoints"
    host = os.getenv("HYDRO_PROGRAM3D_HOST", "0.0.0.0")
    port = int(os.getenv("HYDRO_PROGRAM3D_PORT", "8093"))
    return ServiceSettings(
        service_root=service_root,
        algorithm_dir=algorithm_dir,
        data_dir=data_dir,
        checkpoint_dir=checkpoint_dir,
        host=host,
        port=port,
        nacos_enabled=os.getenv("NACOS_ENABLED", "true").lower() == "true",
        nacos_server_addr=os.getenv("NACOS_SERVER_ADDR", "localhost:8848"),
        nacos_namespace=os.getenv("NACOS_NAMESPACE", "public"),
        nacos_group=os.getenv("NACOS_GROUP", "DEFAULT_GROUP"),
        nacos_cluster=os.getenv("NACOS_CLUSTER", "DEFAULT"),
        nacos_service_name=os.getenv("NACOS_SERVICE_NAME", "hydro-program3d"),
        nacos_ip=os.getenv("NACOS_IP", ""),
        nacos_heartbeat_interval_seconds=float(os.getenv("NACOS_HEARTBEAT_INTERVAL_SECONDS", "5")),
    )
