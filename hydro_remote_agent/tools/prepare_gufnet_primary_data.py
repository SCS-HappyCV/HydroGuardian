from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare exact wcs10m_primary tiles for GUFNet training.")
    parser.add_argument("--split-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    split_root = args.split_root.resolve()
    data_root = args.data_root.resolve()
    output_root = args.output_root.resolve()
    expected = {"train": 1145, "val": 246, "test": 245}
    ids_by_split: dict[str, set[str]] = {}
    rows_by_id: dict[str, dict[str, Any]] = {}
    split_reports: dict[str, Any] = {}
    for split, expected_count in expected.items():
        path = split_root / f"{split}.jsonl"
        rows = _read_jsonl(path)
        ids = [str(row["sample_id"]) for row in rows]
        if len(rows) != expected_count or len(set(ids)) != expected_count:
            raise ValueError(f"{split}: expected {expected_count} unique rows, got {len(rows)}/{len(set(ids))}")
        ids_by_split[split] = set(ids)
        for row in rows:
            sample_id = str(row["sample_id"])
            if sample_id in rows_by_id:
                raise ValueError(f"Cross-split duplicate sample_id: {sample_id}")
            rows_by_id[sample_id] = row
        split_reports[split] = {"path": str(path), "sha256": _sha256(path), "row_count": len(rows)}
    overlaps = {
        "train_val": len(ids_by_split["train"] & ids_by_split["val"]),
        "train_test": len(ids_by_split["train"] & ids_by_split["test"]),
        "val_test": len(ids_by_split["val"] & ids_by_split["test"]),
    }
    if any(overlaps.values()):
        raise ValueError(f"Split overlap detected: {overlaps}")

    total_points = 0
    converted = 0
    reused = 0
    for index, (sample_id, row) in enumerate(rows_by_id.items(), 1):
        folder_id, patch_id = str(row["folder_id"]), str(row["patch_id"])
        source_point = data_root / folder_id / "velodyne" / f"{patch_id}.txt"
        source_image = data_root / folder_id / "image" / f"{patch_id}.png"
        target_point = output_root / folder_id / "velodyne" / f"{patch_id}.pth"
        target_image = output_root / folder_id / "image" / f"{patch_id}.png"
        if not source_point.is_file() or not source_image.is_file():
            raise FileNotFoundError(f"Missing raw asset for {sample_id}: {source_point}, {source_image}")
        target_point.parent.mkdir(parents=True, exist_ok=True)
        target_image.parent.mkdir(parents=True, exist_ok=True)
        if target_point.is_file():
            points = torch.load(target_point, map_location="cpu")
            reused += 1
        else:
            points = np.loadtxt(source_point, dtype=np.float32, ndmin=2)
            if points.shape[1] < 7:
                raise ValueError(f"{sample_id}: expected at least 7 point columns, got {points.shape}")
            temporary = target_point.with_suffix(".pth.tmp")
            torch.save(points, temporary)
            os.replace(temporary, target_point)
            converted += 1
        if int(points.shape[0]) != int(row["num_points"]):
            raise ValueError(f"{sample_id}: manifest points={row['num_points']} prepared={points.shape[0]}")
        total_points += int(points.shape[0])
        if not target_image.exists():
            target_image.symlink_to(source_image)
        if index % 50 == 0 or index == len(rows_by_id):
            print(
                f"GUFNET_PREP_PROGRESS {index}/{len(rows_by_id)} converted={converted} reused={reused}",
                flush=True,
            )

    report = {
        "schema_version": "hydro_agent_bench.gufnet_preprocessing.v1",
        "status": "complete_zero_overlap",
        "split_root": str(split_root),
        "source_data_root": str(data_root),
        "output_root": str(output_root),
        "splits": split_reports,
        "overlaps": overlaps,
        "sample_count": len(rows_by_id),
        "total_points": total_points,
        "converted_count": converted,
        "reused_count": reused,
        "point_dtype": "float32",
        "image_materialization": "absolute_symlink",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
