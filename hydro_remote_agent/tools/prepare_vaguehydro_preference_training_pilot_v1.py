from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_payload(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")
            count += 1
    return count


def scene_id(source_id: str) -> str:
    match = re.match(r"^q:(\d{2}-\d{6})(?:-|:)", source_id)
    if not match:
        raise ValueError(f"cannot parse scene from source_id {source_id!r}")
    return match.group(1)


def source_messages(records: dict[str, dict[str, Any]], source_id: str) -> list[dict[str, Any]]:
    record = records[source_id]
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) < 3:
        raise ValueError(f"source {source_id} does not contain a complete conversation")
    return [dict(message) for message in messages[:2]]


def assistant_json(action: dict[str, Any]) -> str:
    return canonical_json(action)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config_path = (ROOT / args.config).resolve()
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    run_dir = ROOT / cfg["run_dir"]
    if run_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {run_dir}")
    run_dir.mkdir(parents=True)

    preference_path = ROOT / cfg["source_preference_manifest"]
    pair_scores_path = ROOT / cfg["source_pair_scores"]
    audit_path = ROOT / cfg["source_stress_audit"]
    train_source_path = ROOT / cfg["train_source"]
    m1_validation_path = ROOT / cfg["m1_validation_source"]
    m1_manifest_path = ROOT / cfg["m1_manifest"]
    required = [preference_path, pair_scores_path, audit_path, train_source_path, m1_validation_path, m1_manifest_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing required inputs: {missing}")

    preference = json.loads(preference_path.read_text(encoding="utf-8"))
    stress_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if preference.get("status") != "CANDIDATE_ONLY_NOT_TRAINED" or stress_audit.get("integrity_status") != "pass":
        raise ValueError("stress v2 preference source is not independently audited and candidate-only")
    pairs = preference.get("pairs", [])
    if len(pairs) != 132:
        raise ValueError(f"expected 132 preference candidates, got {len(pairs)}")
    for pair in pairs:
        if pair.get("audit_status") != "passed" or pair.get("ambiguous") is not False:
            raise ValueError(f"pair failed audit/ambiguity gate: {pair.get('pair_id')}")
        if not pair.get("suitability", {}).get("dpo", {}).get("eligible"):
            raise ValueError(f"pair is not DPO eligible: {pair.get('pair_id')}")
        if not pair.get("suitability", {}).get("hard_negative_sft", {}).get("eligible"):
            raise ValueError(f"pair is not SFT eligible: {pair.get('pair_id')}")

    train_records = {str(row["id"]): row for row in iter_jsonl(train_source_path) if str(row.get("id")) in {str(p["source_id"]) for p in pairs}}
    if len(train_records) != len({str(p["source_id"]) for p in pairs}):
        raise ValueError("not all preference sources resolve into the M1 train source")

    heldout_families = set(cfg["split"]["held_out_mutation_families"])
    workflow_sources = sorted({str(p["source_id"]) for p in pairs if p["family"] in heldout_families})
    ordered_workflow_sources = sorted(
        workflow_sources,
        key=lambda source: sha256_payload([cfg["split"]["seed"], scene_id(source)]),
    )
    heldout_scenes: list[str] = []
    for source in ordered_workflow_sources:
        scene = scene_id(source)
        if scene not in heldout_scenes:
            heldout_scenes.append(scene)
        if len(heldout_scenes) == int(cfg["split"]["held_out_workflow_scene_count"]):
            break
    heldout_scene_set = set(heldout_scenes)
    if len(heldout_scene_set) != int(cfg["split"]["held_out_workflow_scene_count"]):
        raise ValueError("insufficient unique workflow scenes for held-out split")

    manifest_pairs: list[dict[str, Any]] = []
    train_rows: list[dict[str, Any]] = []
    validation_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    for pair in pairs:
        source_id = str(pair["source_id"])
        family = str(pair["family"])
        scene = scene_id(source_id)
        if scene in heldout_scene_set and family in heldout_families:
            split = "heldout_validation"
        elif scene not in heldout_scene_set and family not in heldout_families:
            split = "train"
        else:
            split = "excluded_cross_cell"
        chosen = pair["chosen"]
        rejected = pair["rejected"]
        record = {
            "pair_id": str(pair["pair_id"]),
            "source_id": source_id,
            "source_scene": scene,
            "mutation_family": family,
            "split": split,
            "audit_status": pair["audit_status"],
            "ambiguous": pair["ambiguous"],
            "mutation_provenance": {
                "stress_run": cfg["source_preference_manifest"],
                "pair_id": pair["pair_id"],
                "family": family,
                "margin_b": pair.get("margin_b"),
            },
            "chosen": chosen,
            "rejected": rejected,
            "chosen_sha256": sha256_payload(chosen),
            "rejected_sha256": sha256_payload(rejected),
            "pair_sha256": sha256_payload({"chosen": chosen, "rejected": rejected}),
        }
        manifest_pairs.append(record)
        if split != "excluded_cross_cell":
            data_row = {
                **record,
                "prompt_messages": source_messages(train_records, source_id),
                "chosen_text": assistant_json(chosen),
                "rejected_text": assistant_json(rejected),
                "source_sample_id": str(train_records[source_id].get("sample_id", "")),
            }
            (train_rows if split == "train" else validation_rows).append(data_row)
        else:
            excluded_rows.append(record)

    train_sources = {row["source_id"] for row in train_rows}
    valid_sources = {row["source_id"] for row in validation_rows}
    train_scenes = {row["source_scene"] for row in train_rows}
    valid_scenes = {row["source_scene"] for row in validation_rows}
    train_families = {row["mutation_family"] for row in train_rows}
    valid_families = {row["mutation_family"] for row in validation_rows}
    overlaps = {
        "source_ids": sorted(train_sources & valid_sources),
        "source_scenes": sorted(train_scenes & valid_scenes),
        "mutation_families": sorted(train_families & valid_families),
        "chosen_sha256": sorted({r["chosen_sha256"] for r in train_rows} & {r["chosen_sha256"] for r in validation_rows}),
        "pair_ids": sorted({r["pair_id"] for r in train_rows} & {r["pair_id"] for r in validation_rows}),
    }
    if any(overlaps.values()):
        raise ValueError(f"split leakage detected: {overlaps}")

    m1_manifest = json.loads(m1_manifest_path.read_text(encoding="utf-8"))
    expected_train_sha = m1_manifest["sources"]["train"]["sha256"]
    expected_valid_sha = m1_manifest["sources"]["valid"]["sha256"]
    if sha256_file(train_source_path) != expected_train_sha or sha256_file(m1_validation_path) != expected_valid_sha:
        raise ValueError("M1 train/validation source hashes do not match the audited manifest")
    validation_candidates = list(iter_jsonl(m1_validation_path))
    validation_candidates.sort(key=lambda row: sha256_payload([cfg["split"]["seed"], row["id"]]))
    m1_rows = validation_candidates[: int(cfg["split"]["m1_validation_count"])]

    write_jsonl(run_dir / "train_pairs.jsonl", train_rows)
    write_jsonl(run_dir / "heldout_pairs.jsonl", validation_rows)
    write_jsonl(run_dir / "m1_validation.jsonl", m1_rows)

    data_manifest = {
        "schema_version": "vaguehydro.preference_data_manifest.v1",
        "created_before_training": True,
        "source_preference_manifest": cfg["source_preference_manifest"],
        "source_manifest_sha256": sha256_file(preference_path),
        "source_pair_scores_sha256": sha256_file(pair_scores_path),
        "source_stress_audit_sha256": sha256_file(audit_path),
        "source_train_sha256": expected_train_sha,
        "m1_validation_sha256": expected_valid_sha,
        "counts": {
            "source_candidate_pairs": len(pairs),
            "train_pairs": len(train_rows),
            "heldout_validation_pairs": len(validation_rows),
            "excluded_cross_cell_pairs": len(excluded_rows),
            "train_source_ids": len(train_sources),
            "heldout_source_ids": len(valid_sources),
            "m1_validation_records": len(m1_rows),
        },
        "family_counts": {
            "train": dict(sorted(Counter(r["mutation_family"] for r in train_rows).items())),
            "heldout_validation": dict(sorted(Counter(r["mutation_family"] for r in validation_rows).items())),
            "excluded_cross_cell": dict(sorted(Counter(r["mutation_family"] for r in excluded_rows).items())),
        },
        "exclusions": {
            "equivalence": int(preference.get("excluded_counts", {}).get("equivalence", -1)),
            "invalid_schema": int(preference.get("excluded_counts", {}).get("invalid_schema", -1)),
            "ambiguous": int(preference.get("excluded_counts", {}).get("ambiguous", -1)),
            "cross_cell_for_group_isolation": len(excluded_rows),
        },
        "pairs": manifest_pairs,
        "dataset_files": {},
        "frozen_240_reads": 0,
    }
    for name in ("train_pairs.jsonl", "heldout_pairs.jsonl", "m1_validation.jsonl"):
        data_manifest["dataset_files"][name] = {"sha256": sha256_file(run_dir / name), "bytes": (run_dir / name).stat().st_size}
    write_json(run_dir / "DATA_MANIFEST.json", data_manifest)

    split_audit = {
        "schema_version": "vaguehydro.preference_split_audit.v1",
        "status": "pass",
        "algorithm": "sha256(split_seed, source_scene) over workflow sources; first six unique scenes held out; two families held out globally; cross cells excluded",
        "heldout_scenes": heldout_scenes,
        "heldout_source_ids": sorted(valid_sources),
        "train_source_ids": sorted(train_sources),
        "train_families": sorted(train_families),
        "heldout_families": sorted(valid_families),
        "overlaps": overlaps,
        "all_overlap_counts_zero": all(not values for values in overlaps.values()),
        "same_gold_across_splits": False,
        "same_family_across_splits": False,
        "validation_is_fixed_no_tuning": True,
        "frozen_240_reads": 0,
    }
    write_json(run_dir / "SPLIT_AUDIT.json", split_audit)

    freeze = dict(cfg)
    freeze["created_before_training"] = True
    freeze["resolved_split"] = {
        "heldout_scenes": heldout_scenes,
        "train_pair_count": len(train_rows),
        "heldout_pair_count": len(validation_rows),
        "excluded_cross_cell_count": len(excluded_rows),
    }
    freeze["input_hashes"] = {
        "config": sha256_file(config_path),
        "preference_manifest": sha256_file(preference_path),
        "train_pairs": sha256_file(run_dir / "train_pairs.jsonl"),
        "heldout_pairs": sha256_file(run_dir / "heldout_pairs.jsonl"),
        "m1_validation": sha256_file(run_dir / "m1_validation.jsonl"),
    }
    write_json(run_dir / "CONFIG_FREEZE.json", freeze)

    protocol = f"""# Pre-Registered Preference Training Pilot v1

## Status

Pre-registered before preflight, evaluation, or training. Frozen-test-240 access is forbidden.

## Arms

- A: original Qwen3-VL VagueHydro SFT LoRA, validation only, zero optimizer steps.
- B: hard-negative SFT from the same base and initial SFT LoRA.
- C: DPO from the same base and initial SFT LoRA with a frozen initial-policy reference.

## Isolation

Train and held-out validation are disjoint by source ID, source scene, chosen payload hash, pair ID, and mutation family. Held-out families are `artifact_reference` and `dag_link`. Cross cells are excluded rather than reassigned. Original M1 validation is a separately fixed regression set and cannot tune training or rewards.

## Frozen Budget

- Seeds: {cfg['seeds']}
- Optimizer steps for B/C: {cfg['optimization']['max_optimizer_steps']}
- Checkpoint/resume boundary: step {cfg['optimization']['checkpoint_step']}
- Batch/accumulation: 1/{cfg['optimization']['gradient_accumulation_steps']}
- LR: {cfg['optimization']['learning_rate']}
- DPO beta: {cfg['optimization']['dpo_beta']}

## Evaluation

Fixed held-out pair accuracy and mean-token log-probability margin; strict AgentRequest legality; Reward A and graph-canonical Reward B with tool/argument/workflow/stop components; equivalence controls; unseen-family/held-out-source performance; and original M1 validation regression. Training reward alone is not an endpoint.

## Release Rule

At least B or C must improve paired margin by >= {cfg['release_gates']['paired_margin_improvement_min']} or accuracy by >= {cfg['release_gates']['or_pair_accuracy_improvement_min']} versus A, avoid > {cfg['release_gates']['strict_legality_drop_max']} legality loss, avoid > {cfg['release_gates']['m1_reward_a_drop_max']} M1 Reward-A loss, and improve margin in at least {cfg['release_gates']['winning_seed_count_min']}/3 seeds. Failure blocks formal training.
"""
    (run_dir / "PRE_REGISTERED_PROTOCOL.md").write_text(protocol, encoding="utf-8")
    lock_files = ["PRE_REGISTERED_PROTOCOL.md", "CONFIG_FREEZE.json", "DATA_MANIFEST.json", "SPLIT_AUDIT.json"]
    lock = {
        "schema_version": "vaguehydro.preference_preregistration_lock.v1",
        "locked_before_preflight_or_training": True,
        "files": {name: sha256_file(run_dir / name) for name in lock_files},
    }
    write_json(run_dir / "PREREGISTRATION_LOCK.json", lock)
    print(canonical_json({"status": "prepared", "run_dir": str(run_dir), "train_pairs": len(train_rows), "heldout_pairs": len(validation_rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
