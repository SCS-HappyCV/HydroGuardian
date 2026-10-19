from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from hydro_remote_agent.service.asset_preview import AssetPreviewService
from hydro_remote_agent.service.assets import ArtifactRecord


class LocalAssetStore:
    def __init__(self, source: Path) -> None:
        self.source = source
        self.downloads = 0

    def download(self, record: ArtifactRecord, target: str | Path) -> Path:
        self.downloads += 1
        shutil.copyfile(self.source, target)
        return Path(target)


def test_asset_preview_is_resized_and_cached(tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    Image.new("RGB", (120, 60), (24, 96, 128)).save(source)
    store = LocalAssetStore(source)
    service = AssetPreviewService(store, tmp_path / "cache")
    record = ArtifactRecord(
        artifact_id="art_preview",
        bucket="input",
        object_key="source.tif",
        media_type="image/tiff",
        size_bytes=source.stat().st_size,
        sha256="preview-sha",
    )

    first = service.render(record, max_dimension=512)
    second = service.render(record, max_dimension=512)

    assert first == second
    assert store.downloads == 1
    with Image.open(first) as preview:
        assert preview.format == "WEBP"
        assert preview.size == (120, 60)
