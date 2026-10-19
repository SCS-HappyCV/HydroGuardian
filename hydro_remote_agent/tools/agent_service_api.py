from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.api import create_app
from hydro_remote_agent.service.store_factory import create_job_store
from hydro_remote_agent.service.websocket_hub import WorkerHub
from hydro_remote_agent.service.assets import ArtifactCatalog, MinioAssetStore
from hydro_remote_agent.service.infra import NullEventBus, RabbitEventBus, RedisPresence


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the VagueHydro Agent HTTP API.")
    parser.add_argument("--db", required=True)
    parser.add_argument(
        "--registry", default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
    )
    parser.add_argument("--allowed-asset-root", action="append", default=[])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--worker-secret", default=os.getenv("WORKER_SECRET", ""))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--minio-endpoint", default=os.getenv("MINIO_ENDPOINT", ""))
    parser.add_argument("--minio-public-endpoint", default=os.getenv("MINIO_PUBLIC_ENDPOINT", ""))
    parser.add_argument("--minio-access-key", default=os.getenv("MINIO_ACCESS_KEY", ""))
    parser.add_argument("--minio-secret-key", default=os.getenv("MINIO_SECRET_KEY", ""))
    parser.add_argument("--minio-secure", action="store_true", default=os.getenv("MINIO_SECURE", "false").lower() == "true")
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", ""))
    parser.add_argument("--rabbitmq-url", default=os.getenv("RABBITMQ_URL", ""))
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Agent API requires uvicorn") from exc
    database = args.database_url or args.db
    store = create_job_store(database)
    catalog_database = database if database.startswith(("postgresql://", "postgresql+psycopg://")) else None
    catalog = ArtifactCatalog(catalog_database)
    asset_store = None
    if args.minio_endpoint:
        asset_store = MinioAssetStore(
            args.minio_endpoint, args.minio_access_key, args.minio_secret_key,
            secure=args.minio_secure,
            public_endpoint=args.minio_public_endpoint or None,
        )
    presence = RedisPresence(args.redis_url) if args.redis_url else None
    event_bus = RabbitEventBus(args.rabbitmq_url) if args.rabbitmq_url else NullEventBus()
    app = create_app(
        store,
        load_tool_registry(args.registry),
        allowed_asset_roots=args.allowed_asset_root,
        worker_hub=WorkerHub(
            worker_secret=args.worker_secret,
            artifact_catalog=catalog,
            presence=presence,
            store=store,
        ),
        asset_store=asset_store,
        artifact_catalog=catalog,
        event_bus=event_bus,
        presence=presence,
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        ws="websockets",
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
