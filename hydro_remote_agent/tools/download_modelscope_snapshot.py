from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
from typing import Optional, Sequence


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Download and inventory a ModelScope model snapshot.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    from modelscope import snapshot_download

    local_path = Path(config["local_path"])
    local_path.parent.mkdir(parents=True, exist_ok=True)
    resolved = Path(snapshot_download(
        model_id=str(config["modelscope_model_id"]),
        revision=str(config["modelscope_revision"]),
        local_dir=str(local_path),
    ))
    required = [resolved / "config.json", resolved / "model.safetensors.index.json"]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"downloaded snapshot is incomplete: {missing}")
    shards = sorted(resolved.glob("model-*.safetensors"))
    if not shards:
        raise RuntimeError("downloaded snapshot has no model weight shards")
    files = [path for path in resolved.rglob("*") if path.is_file()]
    manifest = {
        "schema_version": "vague_hydro.external_model_manifest.v1",
        "model_id": str(config["model_id"]),
        "modelscope_model_id": str(config["modelscope_model_id"]),
        "requested_revision": str(config["modelscope_revision"]),
        "local_path": str(resolved),
        "python": platform.python_version(),
        "file_count": len(files),
        "weight_shard_count": len(shards),
        "total_bytes": sum(path.stat().st_size for path in files),
        "config_sha256": _sha256(resolved / "config.json"),
        "weight_index_sha256": _sha256(resolved / "model.safetensors.index.json"),
        "weight_shard_sha256": {path.name: _sha256(path) for path in shards},
    }
    manifest_path = resolved / "vaguehydro_external_model_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"MODELSCOPE_SNAPSHOT_OK model={manifest['model_id']} "
        f"shards={len(shards)} bytes={manifest['total_bytes']} path={resolved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
