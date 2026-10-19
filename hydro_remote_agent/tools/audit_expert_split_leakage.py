from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sample_keys(rows: Iterable[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(row["folder_id"]).zfill(2), str(row["patch_id"]).zfill(6))
        for row in rows
    }


def legacy_training_keys(root: Path, folders: Iterable[str]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for folder in folders:
        normalized = str(folder).zfill(2)
        for path in (root / normalized / "velodyne").glob("*"):
            if path.is_file():
                keys.add((normalized, path.stem))
    return keys


def audit(split_path: Path, legacy_root: Path, folders: Iterable[str]) -> dict[str, Any]:
    test = sample_keys(load_jsonl(split_path))
    training = legacy_training_keys(legacy_root, folders)
    overlap = sorted(test & training)
    return {
        "schema_version": "hydro_agent_bench.split_leakage_audit.v1",
        "status": "leakage_detected" if overlap else "clean",
        "split_path": str(split_path.resolve()),
        "legacy_root": str(legacy_root.resolve()),
        "legacy_training_file_count": len(training),
        "evaluation_sample_count": len(test),
        "overlap_count": len(overlap),
        "overlap_rate": len(overlap) / len(test) if test else None,
        "overlap_examples": [f"{folder}_{patch}" for folder, patch in overlap[:20]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit tile overlap between an evaluation split and a legacy folder-based training set.")
    parser.add_argument("--split", required=True, type=Path)
    parser.add_argument("--legacy-root", required=True, type=Path)
    parser.add_argument("--folders", nargs="+", default=["00", "01", "02"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.split, args.legacy_root, args.folders)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 2 if report["status"] == "leakage_detected" else 0


if __name__ == "__main__":
    raise SystemExit(main())
