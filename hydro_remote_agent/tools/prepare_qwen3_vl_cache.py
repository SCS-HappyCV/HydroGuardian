from __future__ import annotations

import argparse
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


def collect_files(source: Path, image_only: bool = False) -> List[Path]:
    if image_only:
        return sorted(path for path in source.glob("*/image/*") if path.is_file())
    return sorted(path for path in source.rglob("*") if path.is_file())


def copy_one(source: Path, source_root: Path, target_root: Path) -> Tuple[int, bool]:
    target = target_root / source.relative_to(source_root)
    size = source.stat().st_size
    if target.is_file() and target.stat().st_size == size:
        return size, False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    shutil.copy2(source, temporary)
    os.replace(temporary, target)
    return size, True


def copy_tree(source: Path, target: Path, workers: int, image_only: bool) -> dict:
    files = collect_files(source, image_only=image_only)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda path: copy_one(path, source, target), files))
    return {
        "source": str(source),
        "target": str(target),
        "file_count": len(files),
        "total_bytes": sum(size for size, _ in results),
        "copied_file_count": sum(int(copied) for _, copied in results),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Cache Qwen3-VL weights and WCS10M images.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--skip-model", action="store_true")
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    workers = int(config.get("workers", 8))
    reports = []
    if not args.skip_model:
        reports.append(
            copy_tree(Path(config["model_source"]), Path(config["model_target"]), workers, False)
        )
    reports.append(
        copy_tree(Path(config["image_source"]), Path(config["image_target"]), workers, True)
    )
    manifest = {
        "schema_version": "vague_hydro.runtime_cache.v1",
        "status": "passed",
        "entries": reports,
    }
    manifest_path = Path(config["manifest"])
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"QWEN3_VL_CACHE_OK files={sum(item['file_count'] for item in reports)} bytes={sum(item['total_bytes'] for item in reports)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
