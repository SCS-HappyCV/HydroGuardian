"""Preregister v2 gold lengths, contrast-bearing M1 sample set, and all gates."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from transformers import AutoProcessor

from hydro_remote_agent.tools.train_vaguehydro_r_m2_grpo_smoke import gold_action


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def nearest_rank(values: list[int], quantile: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def describe_lengths(values: list[int]) -> dict[str, Any]:
    return {
        "count": len(values),
        "p50": nearest_rank(values, 0.50),
        "p90": nearest_rank(values, 0.90),
        "p95": nearest_rank(values, 0.95),
        "p99": nearest_rank(values, 0.99),
        "max": max(values),
        "mean": sum(values) / len(values),
    }


def round_up(value: int, multiple: int) -> int:
    return int(math.ceil(value / multiple) * multiple)


def walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)


def structural_features(request: Mapping[str, Any], token_length: int, cfg: Mapping[str, Any]) -> dict[str, Any]:
    action = request["action"]
    action_type = str(action["type"])
    intent = str(request.get("intent", "unknown"))
    expected = request.get("expected_output", {})
    expected_signature = f"{expected.get('type', 'unknown')}|{expected.get('coordinate_space', 'unknown')}"
    confusable_family = set(cfg["contrast_selection"]["confusable_tool_family"])
    if action_type == "tool_call":
        tools = [str(action.get("tool", "unknown"))]
        argument_keys = sorted(action.get("arguments", {}).keys())
        argument_slots = len(argument_keys)
        workflow_edges = 0
        artifact_references = 0
        verification_modes = [str(action.get("verification", "auto"))]
        contrast_axis = "tool_argument"
    elif action_type == "workflow":
        steps = action.get("steps", [])
        tools = [str(step.get("tool", "unknown")) for step in steps]
        argument_keys = sorted({key for step in steps for key in step.get("arguments", {})})
        argument_slots = sum(len(step.get("arguments", {})) for step in steps)
        workflow_edges = sum(len(step.get("depends_on", [])) for step in steps)
        artifact_references = sum(text.count("${") for text in walk_strings(steps))
        verification_modes = sorted({str(step.get("verification", "auto")) for step in steps})
        contrast_axis = "workflow_graph"
    else:
        tools = []
        argument_keys = sorted(key for key in action if key != "type")
        argument_slots = len(argument_keys)
        workflow_edges = 0
        artifact_references = 0
        verification_modes = []
        contrast_axis = "stop"
    confusable_tool_count = sum(tool in confusable_family for tool in tools)
    if action_type == "workflow":
        priority_score = 20 * len(set(tools)) + 8 * workflow_edges + 8 * artifact_references + 2 * argument_slots + token_length
    elif action_type == "tool_call":
        priority_score = 20 * confusable_tool_count + 4 * argument_slots + 3 * len(argument_keys) + token_length
    else:
        priority_score = 5 * len(argument_keys) + token_length
    structure = {
        "gold_contrast_axis": contrast_axis,
        "intent": intent,
        "expected_output_signature": expected_signature,
        "tool_sequence": tools,
        "unique_tool_count": len(set(tools)),
        "confusable_tool_count": confusable_tool_count,
        "argument_keys": argument_keys,
        "argument_slots": argument_slots,
        "workflow_edge_count": workflow_edges,
        "artifact_reference_count": artifact_references,
        "verification_modes": verification_modes,
        "gold_token_length": token_length,
        "contrast_priority_score": priority_score,
    }
    structure["structural_signature"] = sha256_text(canonical_json({key: value for key, value in structure.items() if key not in {"gold_token_length", "contrast_priority_score"}}))
    structure["tool_sequence_signature"] = ">".join(tools) if tools else "none"
    return structure


def parameter_complexity(slots: int, cfg: Mapping[str, Any]) -> str:
    bins = cfg["sampling"]["parameter_complexity_bins"]
    if slots <= int(bins["low_max"]):
        return "low"
    if slots <= int(bins["medium_max"]):
        return "medium"
    return "high"


def seeded_rank(seed: int, identifier: str) -> str:
    return sha256_text(f"{seed}:{identifier}")


def select_contrast_rows(candidates: list[dict[str, Any]], quota: int, seed: int) -> list[dict[str, Any]]:
    remaining = list(candidates)
    chosen: list[dict[str, Any]] = []
    used_structures: set[str] = set()
    used_tools: set[str] = set()
    used_intents: set[str] = set()
    for _ in range(quota):
        ranked = sorted(
            remaining,
            key=lambda row: (
                -(row["structural_signature"] not in used_structures),
                -(row["tool_sequence_signature"] not in used_tools),
                -(row["intent"] not in used_intents),
                -int(row["contrast_priority_score"]),
                seeded_rank(seed, row["id"]),
            ),
        )
        picked = ranked[0]
        chosen.append(picked)
        used_structures.add(picked["structural_signature"])
        used_tools.add(picked["tool_sequence_signature"])
        used_intents.add(picked["intent"])
        remaining = [row for row in remaining if row["id"] != picked["id"]]
    return chosen


def run(config_path: Path, root: Path) -> int:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    source = root / cfg["train_source"]
    output = root / cfg["output"]
    if output.exists():
        raise RuntimeError("v2 output already exists; refusing to overwrite or mutate it")
    output.mkdir(parents=True)
    processor = AutoProcessor.from_pretrained(cfg["base_model"], local_files_only=True)
    tokenizer = processor.tokenizer

    rows: list[dict[str, Any]] = []
    lengths: dict[str, list[int]] = defaultdict(list)
    with source.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            record = json.loads(raw_line.decode("utf-8"))
            request = gold_action(record)
            action_type = str(request["action"]["type"])
            raw_gold = canonical_json(request)
            token_length = len(tokenizer.encode(raw_gold, add_special_tokens=False))
            lengths[action_type].append(token_length)
            features = structural_features(request, token_length, cfg)
            sample_id = str(record.get("sample_id", record["id"]))
            row = {
                "id": str(record["id"]),
                "source_line_number": line_number,
                "source_line_sha256": hashlib.sha256(raw_line).hexdigest(),
                "sample_id": sample_id,
                "image": str(record["images"][0]),
                "language": str(record.get("language", "unknown")),
                "scene_region": sample_id.split("_")[0].split("-")[0],
                "ambiguity_level": str(record.get("ambiguity_level", "unknown")),
                "difficulty": cfg["sampling"]["difficulty_mapping"].get(str(record.get("ambiguity_level")), "unknown"),
                "action_type": action_type,
                "gold_action": request,
                "gold_action_sha256": sha256_text(raw_gold),
                **features,
            }
            row["parameter_complexity"] = parameter_complexity(int(row["argument_slots"]), cfg)
            rows.append(row)

    required_actions = list(cfg["sampling"]["action_types"])
    absent_actions = list(cfg["sampling"]["requested_but_absent_action_types"])
    if any(lengths.get(name) for name in absent_actions):
        raise RuntimeError("A preregistered absent action is present; revise before generation")
    if any(not lengths.get(name) for name in required_actions):
        raise RuntimeError("A required action type is absent")
    length_stats = {name: describe_lengths(lengths[name]) for name in sorted(lengths)}
    policy = cfg["length_budget_policy"]
    budgets = {}
    for action_type in required_actions:
        raw_budget = int(length_stats[action_type][policy["quantile"]]) + int(policy["margin_tokens"][action_type])
        budgets[action_type] = max(int(policy["minimum_tokens"][action_type]), round_up(raw_budget, int(policy["round_up_multiple"])))
    created_at = datetime.now(timezone.utc).isoformat()
    length_report = {
        "schema_version": "vaguehydro.gold_length_distribution.v2",
        "created_at": created_at,
        "source": {"path": cfg["train_source"], "bytes": source.stat().st_size, "sha256": sha256_file(source), "split": "M1_train_only"},
        "encoding": {"base_model": cfg["base_model"], "serialization": "canonical JSON; UTF-8; sort_keys; compact separators", "add_special_tokens": False, "percentile_method": "nearest_rank"},
        "by_action_type": length_stats,
        "fixed_max_new_tokens": budgets,
        "budget_policy": policy,
        "frozen_test_reads": 0,
    }
    length_path = output / "GOLD_LENGTH_DISTRIBUTION.json"
    write_json(length_path, length_report)

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[(row["action_type"], row["difficulty"])].append(row)
    selected: list[dict[str, Any]] = []
    quota = int(cfg["sampling"]["quota_per_action_difficulty_cell"])
    for action_type in required_actions:
        for difficulty in ("easy", "medium", "hard"):
            candidates = buckets[(action_type, difficulty)]
            if len(candidates) < quota:
                raise RuntimeError(f"Insufficient M1 rows for {action_type}/{difficulty}")
            selected.extend(select_contrast_rows(candidates, quota, int(cfg["seed"])))
    if len(selected) != int(cfg["sampling"]["total_samples"]) or len({row["id"] for row in selected}) != len(selected):
        raise RuntimeError("Fixed selection count or uniqueness check failed")

    plan = {
        "schema_version": "vaguehydro.variance_profile.preregistration.v2",
        "created_at": created_at,
        "state": "FROZEN_BEFORE_GENERATION",
        "config": cfg,
        "config_sha256": sha256_file(config_path),
        "gold_length_distribution_path": str(length_path.relative_to(root)),
        "gold_length_distribution_sha256": sha256_file(length_path),
        "fixed_max_new_tokens": budgets,
        "selection_algorithm": {
            "outer_quota": "4 rows per action_type x difficulty cell",
            "inner_priority": cfg["contrast_selection"]["priority"],
            "inputs": ["gold action", "gold tool sequence", "gold argument keys", "gold workflow edges", "gold artifact references", "gold stop fields", "intent", "expected output", "seeded ID hash"],
            "forbidden_inputs": ["model completion", "candidate reward", "frozen-test row", "validation row"],
        },
        "gates": cfg["preregistered_gates"],
        "immutable_after_generation_starts": ["sample IDs", "source lines", "budgets", "G", "sampling parameters", "reward", "completion gate", "variance gate"],
        "forbidden_sources": ["frozen_test", "gold_240", "validation", "model outputs for selection", "reward values for selection"],
        "coverage_note": {"clarification": "absent from M1 train", "abstain": "absent from M1 train"},
    }
    plan_path = output / "PRE_REGISTERED_SAMPLING_PLAN.json"
    write_json(plan_path, plan)
    manifest_records = []
    for index, row in enumerate(selected):
        item = dict(row)
        item["manifest_index"] = index
        item["generation_seed"] = int(cfg["seed"]) + index
        item["max_new_tokens"] = budgets[row["action_type"]]
        manifest_records.append(item)
    manifest = {
        "schema_version": "vaguehydro.variance_profile.data_manifest.v2",
        "created_at": created_at,
        "state": "FROZEN_BEFORE_GENERATION",
        "source": length_report["source"],
        "record_count": len(manifest_records),
        "group_size": int(cfg["sampling"]["group_size"]),
        "expected_candidate_count": len(manifest_records) * int(cfg["sampling"]["group_size"]),
        "records": manifest_records,
        "selected_distribution": {
            "action_type": dict(sorted(Counter(row["action_type"] for row in manifest_records).items())),
            "difficulty": dict(sorted(Counter(row["difficulty"] for row in manifest_records).items())),
            "language": dict(sorted(Counter(row["language"] for row in manifest_records).items())),
            "parameter_complexity": dict(sorted(Counter(row["parameter_complexity"] for row in manifest_records).items())),
            "scene_region": dict(sorted(Counter(row["scene_region"] for row in manifest_records).items())),
            "gold_contrast_axis": dict(sorted(Counter(row["gold_contrast_axis"] for row in manifest_records).items())),
            "action_x_difficulty": dict(sorted(Counter(f"{row['action_type']}|{row['difficulty']}" for row in manifest_records).items())),
            "tool_sequence": dict(sorted(Counter(row["tool_sequence_signature"] for row in manifest_records).items())),
        },
        "selection_used_model_outputs": False,
        "selection_used_rewards": False,
        "frozen_test_reads": 0,
        "posthoc_changes": 0,
    }
    manifest_path = output / "PROFILE_DATA_MANIFEST.json"
    write_json(manifest_path, manifest)
    lock = {
        "state": "LOCKED_BEFORE_GENERATION",
        "created_at": created_at,
        "config_sha256": sha256_file(config_path),
        "source_sha256": sha256_file(source),
        "gold_length_distribution_sha256": sha256_file(length_path),
        "sampling_plan_sha256": sha256_file(plan_path),
        "profile_data_manifest_sha256": sha256_file(manifest_path),
        "generation_started": False,
    }
    write_json(output / "PREREGISTRATION_LOCK.json", lock)
    print(json.dumps({"status": "locked", "samples": len(manifest_records), "budgets": budgets, "output": str(output)}, ensure_ascii=False))
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
