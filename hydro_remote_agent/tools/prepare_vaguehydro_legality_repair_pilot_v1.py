from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical(row) + "\n")


def unique_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        output.setdefault(str(row["source_id"]), row)
    return [output[key] for key in sorted(output)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config_path = ROOT / args.config
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    run_dir = ROOT / cfg["run_dir"]
    if run_dir.exists():
        raise FileExistsError(f"refusing to overwrite {run_dir}")
    run_dir.mkdir(parents=True)
    source = ROOT / cfg["source_preference_run"]
    train_pairs_path = source / "train_pairs.jsonl"
    heldout_pairs_path = source / "heldout_pairs.jsonl"
    m1_path = source / "m1_validation.jsonl"
    for path in (train_pairs_path, heldout_pairs_path, m1_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    train_pairs = read_jsonl(train_pairs_path)
    heldout_pairs = read_jsonl(heldout_pairs_path)
    m1_rows = read_jsonl(m1_path)
    train_sources = unique_sources(train_pairs)
    heldout_sources = unique_sources(heldout_pairs)[: int(cfg["evaluation"]["heldout_source_count"])]
    m1_rows = m1_rows[: int(cfg["evaluation"]["m1_validation_count"])]
    serialization_rows = []
    for row in train_sources:
        serialization_rows.append({
            "id": row["source_id"],
            "source_scene": row["source_scene"],
            "prompt_messages": row["prompt_messages"],
            "chosen": row["chosen"],
            "chosen_text": canonical(row["chosen"]),
            "source": "M1_train_audited_chosen",
        })
    eval_heldout = [{
        "id": row["source_id"], "source_scene": row["source_scene"],
        "prompt_messages": row["prompt_messages"], "chosen": row["chosen"],
        "source": "heldout_unseen_family",
    } for row in heldout_sources]
    eval_m1 = [{
        "id": row["id"], "prompt_messages": row["messages"][:2],
        "chosen": json.loads(row["messages"][-1]["content"]), "source": "M1_validation",
    } for row in m1_rows]
    train_ids = {row["id"] for row in serialization_rows}
    heldout_ids = {row["id"] for row in eval_heldout}
    m1_ids = {row["id"] for row in eval_m1}
    overlaps = {
        "train_heldout": sorted(train_ids & heldout_ids),
        "train_m1_validation": sorted(train_ids & m1_ids),
        "heldout_m1_validation": sorted(heldout_ids & m1_ids),
    }
    if any(overlaps.values()):
        raise ValueError(f"split leakage: {overlaps}")
    files = {
        "serialization_train.jsonl": serialization_rows,
        "heldout_eval.jsonl": eval_heldout,
        "m1_validation_eval.jsonl": eval_m1,
    }
    for name, rows in files.items():
        write_jsonl(run_dir / name, rows)
    manifest = {
        "schema_version": "vaguehydro.legality_data.v1",
        "created_before_preflight": True,
        "counts": {name: len(rows) for name, rows in files.items()},
        "files": {name: {"sha256": sha256(run_dir / name), "bytes": (run_dir / name).stat().st_size} for name in files},
        "source_files": {str(path.relative_to(ROOT)): sha256(path) for path in (train_pairs_path, heldout_pairs_path, m1_path)},
        "frozen_240_path_read": False,
    }
    split = {"status": "pass", "overlaps": overlaps, "all_zero": all(not value for value in overlaps.values()), "frozen_240_reads": 0}
    freeze = dict(cfg)
    freeze["created_before_preflight"] = True
    freeze["input_hashes"] = {"config": sha256(config_path), **{name: manifest["files"][name]["sha256"] for name in files}}
    write_json(run_dir / "DATA_MANIFEST.json", manifest)
    write_json(run_dir / "SPLIT_AUDIT.json", split)
    write_json(run_dir / "CONFIG_FREEZE.json", freeze)
    protocol = """# VagueHydro Legality Repair Pilot v1

Pre-registered before preflight and generation. A is unconstrained control; B is online schema-constrained decoding; C is serialization-only SFT with unconstrained generation; D combines C and B. All arms use the same fixed held-out and M1-validation records and three seeds. Forced completions, post-hoc JSON repair, failed-output filtering, success resampling, frozen-240 reads, experts, and Verifier calls are forbidden.

Release requires at least one repair arm to reach >=80% strict legality on both held-out and M1 validation, Reward-A >=0.5 on both splits, and pass in at least two seeds. This is a pilot, not formal training.
"""
    (run_dir / "PRE_REGISTERED_PROTOCOL.md").write_text(protocol, encoding="utf-8")
    print(canonical({"status": "prepared", "run_dir": str(run_dir), "counts": manifest["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
