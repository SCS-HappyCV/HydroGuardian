from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Optional, Sequence


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download a pinned Qwen3-VL snapshot.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--max-workers", type=int, default=4)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    model_id = str(config["model_id"])
    revision = str(config["revision"])
    local_path = Path(config["local_path"])
    endpoint = str(config["download_endpoint"])

    os.environ["HF_ENDPOINT"] = endpoint
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import HfApi, snapshot_download

    info = HfApi(endpoint=endpoint).model_info(model_id, revision=revision)
    if info.sha != revision:
        raise RuntimeError(f"resolved revision {info.sha!r} does not match {revision!r}")
    local_path.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=model_id,
        revision=revision,
        local_dir=str(local_path),
        endpoint=endpoint,
        max_workers=max(int(args.max_workers), 1),
    )

    required = [
        local_path / "config.json",
        local_path / "generation_config.json",
        local_path / "preprocessor_config.json",
        local_path / "model.safetensors.index.json",
    ]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"downloaded snapshot is incomplete: {missing}")
    shards = sorted(local_path.glob("model-*.safetensors"))
    if not shards:
        raise RuntimeError("downloaded snapshot has no model weight shards")
    files = [path for path in local_path.rglob("*") if path.is_file()]
    manifest = {
        "schema_version": "vague_hydro.backbone_manifest.v1",
        "model_id": model_id,
        "revision": revision,
        "resolved_revision": info.sha,
        "download_endpoint": endpoint,
        "local_path": str(local_path),
        "python": platform.python_version(),
        "file_count": len(files),
        "weight_shard_count": len(shards),
        "total_bytes": sum(path.stat().st_size for path in files),
        "config_sha256": sha256_file(local_path / "config.json"),
        "weight_index_sha256": sha256_file(local_path / "model.safetensors.index.json"),
    }
    manifest_path = local_path / "vaguehydro_model_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"QWEN3_VL_DOWNLOAD_OK revision={revision} shards={len(shards)} "
        f"bytes={manifest['total_bytes']} path={local_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
