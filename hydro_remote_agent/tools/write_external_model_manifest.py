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
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze an external model snapshot manifest.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--model-path", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    model_path = Path(args.model_path).resolve()
    config_path = model_path / "config.json"
    shards = sorted(
        path
        for pattern in ("*.safetensors", "pytorch_model*.bin")
        for path in model_path.glob(pattern)
        if path.is_file()
    )
    if not config_path.is_file() or not shards:
        raise FileNotFoundError("External model snapshot is missing config.json or weights")
    files = [path for path in model_path.rglob("*") if path.is_file()]
    manifest = {
        "schema_version": "vague_hydro.external_model_manifest.v1",
        "model_id": str(config["model_id"]),
        "source": str(config.get("source", "HuggingFace")),
        "requested_revision": str(config["revision"]),
        "local_path": str(model_path),
        "python": platform.python_version(),
        "file_count": len(files),
        "weight_shard_count": len(shards),
        "total_bytes": sum(path.stat().st_size for path in files),
        "config_sha256": _sha256(config_path),
        "weight_shard_sha256": {path.name: _sha256(path) for path in shards},
    }
    output = model_path / "vaguehydro_external_model_manifest.json"
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"EXTERNAL_MODEL_MANIFEST_OK model={manifest['model_id']} "
        f"shards={len(shards)} bytes={manifest['total_bytes']} path={model_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
