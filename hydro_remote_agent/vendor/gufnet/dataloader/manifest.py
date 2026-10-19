from __future__ import annotations

import json
from pathlib import Path


def manifest_file_paths(manifest_path, data_path, num_vote):
    """Resolve a frozen tile manifest to preprocessed GUFNet samples in manifest order."""
    manifest_path = Path(manifest_path)
    data_path = Path(data_path)
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    seen = set()
    for row in rows:
        sample_id = str(row["sample_id"])
        if sample_id in seen:
            raise ValueError(f"Duplicate sample_id {sample_id!r} in {manifest_path}")
        seen.add(sample_id)

    paths = []
    for row in rows:
        sample_id = str(row["sample_id"])
        point_path = data_path / str(row["folder_id"]) / "velodyne" / f"{row['patch_id']}.pth"
        image_path = data_path / str(row["folder_id"]) / "image" / f"{row['patch_id']}.png"
        if not point_path.is_file() or not image_path.is_file():
            raise FileNotFoundError(
                f"Missing preprocessed GUFNet asset for {sample_id}: point={point_path}, image={image_path}"
            )
        paths.extend([str(point_path.resolve())] * num_vote)
    return paths
