from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rows(path):
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def compact_request(value):
    value = json.loads(json.dumps(value, ensure_ascii=False))
    value.pop("expected_output", None)
    action = value.get("action", {})
    if action.get("verification") == "auto":
        action.pop("verification", None)
    for step in action.get("steps", []):
        if step.get("verification") == "auto":
            step.pop("verification", None)
        if step.get("depends_on") == []:
            step.pop("depends_on", None)
    return value


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path, values):
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for value in values:
            f.write(canonical(value) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    cfg_path = ROOT / args.config
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    run_dir = ROOT / cfg["run_dir"]
    if run_dir.exists():
        raise FileExistsError(run_dir)
    run_dir.mkdir(parents=True)
    source = ROOT / cfg["source_preference_run"]
    train_pairs = rows(source / "train_pairs.jsonl")
    heldout_pairs = rows(source / "heldout_pairs.jsonl")
    m1 = rows(source / "m1_validation.jsonl")
    unique = {}
    for row in train_pairs:
        unique.setdefault(str(row["source_id"]), row)
    train = []
    for row in unique.values():
        compact = compact_request(row["chosen"])
        train.append({"id": row["source_id"], "source_scene": row["source_scene"], "prompt_messages": row["prompt_messages"], "chosen": compact, "chosen_text": canonical(compact), "source": "M1_train_compact_legal"})
    heldout = [{"id": row["source_id"], "source_scene": row["source_scene"], "prompt_messages": row["prompt_messages"], "chosen": row["chosen"], "source": "heldout_unseen_family"} for row in list({str(x["source_id"]): x for x in heldout_pairs}.values())[:6]]
    validation = [{"id": row["id"], "prompt_messages": row["messages"][:2], "chosen": json.loads(row["messages"][-1]["content"]), "source": "M1_validation"} for row in m1[:8]]
    files = {"serialization_train.jsonl": train, "heldout_eval.jsonl": heldout, "m1_validation_eval.jsonl": validation}
    ids = {name: {str(x["id"]) for x in values} for name, values in files.items()}
    overlap = {"train_heldout": sorted(ids["serialization_train.jsonl"] & ids["heldout_eval.jsonl"]), "train_m1_validation": sorted(ids["serialization_train.jsonl"] & ids["m1_validation_eval.jsonl"]), "heldout_m1_validation": sorted(ids["heldout_eval.jsonl"] & ids["m1_validation_eval.jsonl"])}
    if any(overlap.values()):
        raise ValueError(overlap)
    for name, values in files.items():
        write_jsonl(run_dir / name, values)
    manifest = {"schema_version": "vaguehydro.legality_data.v3", "compact_target_optional_fields_removed": True, "counts": {name: len(value) for name, value in files.items()}, "files": {name: {"sha256": sha256(run_dir / name), "bytes": (run_dir / name).stat().st_size} for name in files}, "frozen_240_path_read": False}
    write_json(run_dir / "DATA_MANIFEST.json", manifest)
    write_json(run_dir / "SPLIT_AUDIT.json", {"status": "pass", "overlaps": overlap, "all_zero": all(not x for x in overlap.values()), "frozen_240_reads": 0})
    frozen = dict(cfg); frozen["created_before_preflight"] = True; frozen["input_hashes"] = {"config": sha256(cfg_path), **{name: manifest["files"][name]["sha256"] for name in files}}
    write_json(run_dir / "CONFIG_FREEZE.json", frozen)
    (run_dir / "PRE_REGISTERED_PROTOCOL.md").write_text("# VagueHydro Legality Repair Pilot v3\n\nSame fixed splits, seeds, decoder, and evaluation gold as v1/v2. Training targets use compact legal AgentRequest serialization by omitting optional expected_output, default verification, and empty depends_on. Evaluation gold is unchanged. No forced completion, posthoc repair, filtering, retries, frozen-240 reads, experts, Verifier, or formal training. Release gates remain unchanged.\n", encoding="utf-8")
    print(canonical({"status": "prepared", "run_dir": str(run_dir), "counts": manifest["counts"], "compact_target_chars": [len(x["chosen_text"]) for x in train]}))


if __name__ == "__main__":
    main()
