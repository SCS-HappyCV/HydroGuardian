from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence


PACKAGES = (
    "accelerate",
    "bitsandbytes",
    "datasets",
    "deepspeed",
    "peft",
    "torch",
    "transformers",
    "trl",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_versions() -> dict[str, Optional[str]]:
    versions: dict[str, Optional[str]] = {}
    for package in PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def gpu_inventory() -> list[dict[str, Any]]:
    fields = "index,name,memory.used,memory.free,memory.total,utilization.gpu"
    result = subprocess.run(
        ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
        check=True,
        capture_output=True,
        text=True,
    )
    gpus = []
    for line in result.stdout.splitlines():
        values = [value.strip() for value in line.split(",")]
        gpus.append(
            {
                "index": int(values[0]),
                "name": values[1],
                "memory_used_mib": int(values[2]),
                "memory_free_mib": int(values[3]),
                "memory_total_mib": int(values[4]),
                "utilization_percent": int(values[5]),
            }
        )
    return gpus


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Record the VagueHydro-R M2 environment.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))

    import torch

    preservation = {}
    for relative_path in config["m1_preservation_files"]:
        path = root / relative_path
        preservation[relative_path] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    install_log = root / config["output_dir"] / "dependency_install.log"
    report = {
        "schema_version": "vaguehydro_r.m2_environment_manifest.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "python": platform.python_version(),
        "packages": package_versions(),
        "cuda": {
            "available": torch.cuda.is_available(),
            "runtime_version": torch.version.cuda,
            "device_count": torch.cuda.device_count(),
        },
        "gpus": gpu_inventory(),
        "selected_gpu": 0,
        "environment_pins": config["environment_pins"],
        "dependency_install": {
            "log": install_log.relative_to(root).as_posix(),
            "log_sha256": sha256_file(install_log) if install_log.exists() else None,
        },
        "m1_preservation_baseline": preservation,
    }
    output_path = args.output if args.output.is_absolute() else root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"VAGUEHYDRO_R_M2_ENV_OK output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
