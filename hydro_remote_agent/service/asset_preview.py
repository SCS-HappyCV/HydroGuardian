from __future__ import annotations

import os
import threading
from pathlib import Path

from .assets import ArtifactRecord, MinioAssetStore


class AssetPreviewService:
    def __init__(self, asset_store: MinioAssetStore, cache_dir: str | Path) -> None:
        self.asset_store = asset_store
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())

    def render(self, record: ArtifactRecord, max_dimension: int = 2048) -> Path:
        dimension = max(512, min(int(max_dimension), 4096))
        fingerprint = (record.sha256 or str(record.size_bytes or "unknown"))[:16]
        target = self.cache_dir / f"{record.artifact_id}-{fingerprint}-{dimension}.webp"
        if target.is_file() and target.stat().st_size > 0:
            return target

        with self._lock(target.name):
            if target.is_file() and target.stat().st_size > 0:
                return target
            source = self.cache_dir / f".{record.artifact_id}-{fingerprint}.source"
            temporary = target.with_suffix(".tmp.webp")
            try:
                self.asset_store.download(record, source)
                from PIL import Image

                Image.MAX_IMAGE_PIXELS = max(Image.MAX_IMAGE_PIXELS or 0, 350_000_000)
                with Image.open(source) as image:
                    image.thumbnail((dimension, dimension), Image.Resampling.LANCZOS)
                    if image.mode not in {"RGB", "RGBA"}:
                        image = image.convert("RGB")
                    image.save(temporary, format="WEBP", quality=82, method=4)
                os.replace(temporary, target)
            finally:
                source.unlink(missing_ok=True)
                temporary.unlink(missing_ok=True)
        return target
