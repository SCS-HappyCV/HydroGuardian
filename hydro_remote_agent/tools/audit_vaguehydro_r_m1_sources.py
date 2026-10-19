from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Optional, Sequence


def audit_source(path: Path) -> tuple[dict[str, object], set[str]]:
    digest = hashlib.sha256()
    identifiers: set[str] = set()
    rows = 0
    with path.open("rb") as handle:
        for raw_line in handle:
            digest.update(raw_line)
            if not raw_line.strip():
                continue
            row = json.loads(raw_line)
            if not isinstance(row, dict):
                raise ValueError(f"{path} contains a non-object row")
            rows += 1
            identifiers.add(str(row.get("id")))
    return (
        {
            "path": path.as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
            "rows": rows,
            "unique_ids": len(identifiers),
        },
        identifiers,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Independently audit M1 source JSONLs.")
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    paths = {
        "train": root / "hydro_remote_agent/data/vague_hydro_sft_v2/train_curriculum_16360.jsonl",
        "valid": root / "hydro_remote_agent/data/vague_hydro_sft_v2/val_sft.jsonl",
        "frozen_test": root / "runs/hydro_remote_agent/agent_eval_v1/gold_240.jsonl",
    }
    sources: dict[str, dict[str, object]] = {}
    identifiers: dict[str, set[str]] = {}
    for name, path in paths.items():
        sources[name], identifiers[name] = audit_source(path)
        sources[name]["path"] = path.relative_to(root).as_posix()
    report = {
        "schema_version": "vaguehydro_r.m1_remote_source_audit.v1",
        "project_root": root.as_posix(),
        "sources": sources,
        "overlap_counts": {
            "train_frozen": len(identifiers["train"] & identifiers["frozen_test"]),
            "valid_frozen": len(identifiers["valid"] & identifiers["frozen_test"]),
            "train_valid": len(identifiers["train"] & identifiers["valid"]),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
