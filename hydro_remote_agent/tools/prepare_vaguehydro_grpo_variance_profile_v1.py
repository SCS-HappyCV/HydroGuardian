"""Freeze the VagueHydro reward-variance sampling plan before generation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hydro_remote_agent.tools.train_vaguehydro_r_m2_grpo_smoke import gold_action


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parameter_slots(action: Mapping[str, Any]) -> int:
    action_type = str(action.get("type", ""))
    if action_type == "tool_call":
        return len(action.get("arguments", {}))
    if action_type == "workflow":
        return sum(len(step.get("arguments", {})) for step in action.get("steps", []))
    return len([key for key in action if key != "type"])


def slot_bin(count: int, bins: Mapping[str, int]) -> str:
    if count <= int(bins["low_max"]):
        return "low"
    if count <= int(bins["medium_max"]):
        return "medium"
    return "high"


def row_attributes(record: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
    request = gold_action(record)
    action = request["action"]
    slots = parameter_slots(action)
    sample_id = str(record.get("sample_id", record.get("id", "")))
    return {
        "id": str(record["id"]),
        "sample_id": sample_id,
        "action_type": str(action["type"]),
        "difficulty": cfg["sampling"]["difficulty_mapping"].get(str(record.get("ambiguity_level")), "unknown"),
        "ambiguity_level": str(record.get("ambiguity_level", "unknown")),
        "language": str(record.get("language", "unknown")),
        "scene_region": sample_id.split("_")[0].split("-")[0],
        "parameter_slots": slots,
        "parameter_complexity": slot_bin(slots, cfg["sampling"]["parameter_complexity_bins"]),
        "image": str(record["images"][0]),
        "gold_action": request,
    }


def seeded_rank(seed: int, identifier: str) -> str:
    return hashlib.sha256(f"{seed}:{identifier}".encode("utf-8")).hexdigest()


def select_cell(candidates: list[dict[str, Any]], cfg: Mapping[str, Any], cell_index: int) -> list[dict[str, Any]]:
    sampling = cfg["sampling"]
    quota = int(sampling["quota_per_action_difficulty_cell"])
    remaining = list(candidates)
    chosen: list[dict[str, Any]] = []
    for position in range(quota):
        target_complexity = sampling["parameter_target_cycle"][(cell_index + position) % 3]
        target_language = sampling["language_target_cycle"][(cell_index + position) % 3]
        target_region = sampling["region_target_cycle"][(cell_index + position) % 3]
        if not remaining:
            raise RuntimeError("Cell exhausted before fixed quota was met")
        ranked = sorted(
            remaining,
            key=lambda row: (
                row["parameter_complexity"] != target_complexity,
                row["language"] != target_language,
                row["scene_region"] != target_region,
                seeded_rank(int(cfg["seed"]), row["id"]),
            ),
        )
        picked = ranked[0]
        picked = dict(picked)
        picked["selection_target"] = {
            "parameter_complexity": target_complexity,
            "language": target_language,
            "scene_region": target_region,
        }
        picked["selection_target_exact"] = all(
            picked[key] == value for key, value in picked["selection_target"].items()
        )
        chosen.append(picked)
        remaining = [row for row in remaining if row["id"] != picked["id"]]
    return chosen


def run(config_path: Path, root: Path) -> int:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    source = root / cfg["train_source"]
    output = root / cfg["output"]
    output.mkdir(parents=True, exist_ok=True)
    plan_path = output / "PRE_REGISTERED_SAMPLING_PLAN.json"
    manifest_path = output / "PROFILE_DATA_MANIFEST.json"
    if plan_path.exists() or manifest_path.exists():
        raise RuntimeError("Preregistration artifacts already exist; refusing to overwrite")

    records: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    rows = [row_attributes(record, cfg) for record in records]
    available_actions = Counter(row["action_type"] for row in rows)
    required_actions = list(cfg["sampling"]["action_types"])
    absent_claimed = list(cfg["sampling"]["requested_but_absent_action_types"])
    if any(available_actions.get(name, 0) for name in absent_claimed):
        raise RuntimeError("A preregistered absent action type is present; revise config before generation")

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[(row["action_type"], row["difficulty"])].append(row)
    selected: list[dict[str, Any]] = []
    cell_index = 0
    for action_type in required_actions:
        for difficulty in ("easy", "medium", "hard"):
            candidates = buckets[(action_type, difficulty)]
            quota = int(cfg["sampling"]["quota_per_action_difficulty_cell"])
            if len(candidates) < quota:
                raise RuntimeError(f"Insufficient records for {action_type}/{difficulty}: {len(candidates)} < {quota}")
            selected.extend(select_cell(candidates, cfg, cell_index))
            cell_index += 1
    if len(selected) != int(cfg["sampling"]["total_samples"]):
        raise RuntimeError("Selected sample count differs from preregistered total")
    if len({row["id"] for row in selected}) != len(selected):
        raise RuntimeError("Duplicate IDs in fixed manifest")

    created_at = datetime.now(timezone.utc).isoformat()
    plan = {
        "schema_version": "vaguehydro.variance_profile.preregistration.v1",
        "created_at": created_at,
        "state": "FROZEN_BEFORE_GENERATION",
        "config": cfg,
        "config_sha256": sha256_file(config_path),
        "source": {"path": cfg["train_source"], "bytes": source.stat().st_size, "sha256": sha256_file(source)},
        "selection_algorithm": "fixed action x difficulty quotas; deterministic target cycles; SHA256(seed:id) tie-break",
        "available_train_distribution": {
            "count": len(rows),
            "actions": dict(sorted(available_actions.items())),
            "difficulty": dict(sorted(Counter(row["difficulty"] for row in rows).items())),
            "language": dict(sorted(Counter(row["language"] for row in rows).items())),
            "parameter_complexity": dict(sorted(Counter(row["parameter_complexity"] for row in rows).items())),
            "scene_region": dict(sorted(Counter(row["scene_region"] for row in rows).items())),
        },
        "coverage_note": {
            "clarification": "not present in M1 train; no synthetic or external row added",
            "abstain": "not present in M1 train; no synthetic or external row added",
        },
        "immutable_after_generation_starts": ["sample IDs", "quota", "seed", "G", "sampling parameters", "reward", "gate thresholds"],
        "forbidden_sources": ["frozen_test", "gold_240", "validation/frozen-derived manifests"],
    }
    write_json(plan_path, plan)
    plan_sha256 = sha256_file(plan_path)

    public_records = []
    for index, row in enumerate(selected):
        item = dict(row)
        item["manifest_index"] = index
        item["generation_seed"] = int(cfg["seed"]) + index
        item["gold_action_sha256"] = canonical_hash(item["gold_action"])
        public_records.append(item)
    manifest = {
        "schema_version": "vaguehydro.variance_profile.data_manifest.v1",
        "created_at": created_at,
        "state": "FROZEN_BEFORE_GENERATION",
        "plan_path": str(plan_path.relative_to(root)),
        "plan_sha256": plan_sha256,
        "record_count": len(public_records),
        "group_size": int(cfg["sampling"]["group_size"]),
        "expected_candidate_count": len(public_records) * int(cfg["sampling"]["group_size"]),
        "records": public_records,
        "selected_distribution": {
            "action_type": dict(sorted(Counter(row["action_type"] for row in public_records).items())),
            "difficulty": dict(sorted(Counter(row["difficulty"] for row in public_records).items())),
            "language": dict(sorted(Counter(row["language"] for row in public_records).items())),
            "parameter_complexity": dict(sorted(Counter(row["parameter_complexity"] for row in public_records).items())),
            "scene_region": dict(sorted(Counter(row["scene_region"] for row in public_records).items())),
            "action_x_difficulty": dict(sorted(Counter(f"{row['action_type']}|{row['difficulty']}" for row in public_records).items())),
        },
        "frozen_test_reads": 0,
        "posthoc_changes": 0,
    }
    write_json(manifest_path, manifest)
    lock = {
        "plan_sha256": sha256_file(plan_path),
        "manifest_sha256": sha256_file(manifest_path),
        "config_sha256": sha256_file(config_path),
        "source_sha256": sha256_file(source),
        "generation_started": False,
    }
    write_json(output / "PREREGISTRATION_LOCK.json", lock)
    print(json.dumps({"status": "frozen", "samples": len(public_records), "output": str(output)}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    config = args.config if args.config.is_absolute() else root / args.config
    return run(config, root)


if __name__ == "__main__":
    raise SystemExit(main())
