import json
from pathlib import Path

import pytest

from hydro_remote_agent.vendor.gufnet.dataloader.manifest import manifest_file_paths


def test_manifest_file_paths_preserve_frozen_order(tmp_path: Path) -> None:
    rows = [
        {"sample_id": "01_000002", "folder_id": "01", "patch_id": "000002"},
        {"sample_id": "00_000001", "folder_id": "00", "patch_id": "000001"},
    ]
    manifest = tmp_path / "train.jsonl"
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    for row in rows:
        point = tmp_path / row["folder_id"] / "velodyne" / f"{row['patch_id']}.pth"
        image = tmp_path / row["folder_id"] / "image" / f"{row['patch_id']}.png"
        point.parent.mkdir(parents=True, exist_ok=True)
        image.parent.mkdir(parents=True, exist_ok=True)
        point.touch()
        image.touch()

    paths = manifest_file_paths(manifest, tmp_path, num_vote=2)

    assert [Path(path).stem for path in paths] == ["000002", "000002", "000001", "000001"]


def test_manifest_file_paths_reject_duplicates(tmp_path: Path) -> None:
    row = {"sample_id": "00_000001", "folder_id": "00", "patch_id": "000001"}
    manifest = tmp_path / "train.jsonl"
    manifest.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate sample_id"):
        manifest_file_paths(manifest, tmp_path, num_vote=1)
