"""Freeze paired reward A/B, curriculum C, samples, tests, and gates before generation."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hydro_remote_agent.rewards.structural_contrast_reward import COMPONENTS as B_COMPONENTS, WEIGHTS_BY_ACTION
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


def walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)


def nearest_rank(values: list[int], quantile: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def structural_row(record: Mapping[str, Any], line_number: int, line_sha: str, cfg: Mapping[str, Any]) -> dict[str, Any]:
    request = gold_action(record)
    action = request["action"]
    action_type = str(action["type"])
    if action_type == "tool_call":
        steps = []
        tools = [str(action["tool"])]
        arguments = [action.get("arguments", {})]
        edges = 0
        refs = 0
        verification = [str(action.get("verification", "auto"))]
    else:
        steps = action.get("steps", [])
        tools = [str(step["tool"]) for step in steps]
        arguments = [step.get("arguments", {}) for step in steps]
        edges = sum(len(step.get("depends_on", [])) for step in steps)
        refs = sum(text.count("${") for text in walk_strings(steps))
        verification = sorted({str(step.get("verification", "auto")) for step in steps})
    argument_slots = sum(len(value) for value in arguments)
    argument_keys = sorted({str(key) for value in arguments for key in value})
    operations = sorted({str(value.get("operation")) for value in arguments if value.get("operation") is not None})
    sample_id = str(record.get("sample_id", record["id"]))
    structure_payload = {
        "tools": tools, "argument_keys": argument_keys, "steps": len(steps), "edges": edges,
        "refs": refs, "verification": verification, "intent": request.get("intent"),
        "expected_output": request.get("expected_output"), "operations": operations,
    }
    return {
        "id": str(record["id"]), "source_line_number": line_number, "source_line_sha256": line_sha,
        "sample_id": sample_id, "image": str(record["images"][0]), "language": str(record.get("language", "unknown")),
        "scene_region": sample_id.split("_")[0].split("-")[0], "ambiguity_level": str(record.get("ambiguity_level", "unknown")),
        "difficulty": cfg["sampling"]["difficulty_mapping"].get(str(record.get("ambiguity_level")), "unknown"),
        "action_type": action_type, "intent": str(request.get("intent", "unknown")), "gold_action": request,
        "gold_action_sha256": sha256_text(canonical_json(request)), "tool_name": tools[0] if action_type == "tool_call" else None,
        "tool_sequence": tools, "tool_sequence_signature": ">".join(tools), "unique_tool_count": len(set(tools)),
        "step_count": len(steps), "argument_slots": argument_slots, "argument_key_signature": "|".join(argument_keys),
        "edge_count": edges, "artifact_reference_count": refs, "verification_modes": verification,
        "operation_signature": "|".join(operations) if operations else "none",
        "structural_signature": sha256_text(canonical_json(structure_payload)),
    }


def assign_complexity_bands(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    thresholds: dict[str, dict[str, int]] = {}
    for action_type in ("tool_call", "workflow"):
        values = [int(row["argument_slots"]) for row in rows if row["action_type"] == action_type]
        low_max = nearest_rank(values, 1 / 3)
        medium_max = nearest_rank(values, 2 / 3)
        thresholds[action_type] = {"low_max": low_max, "medium_max": medium_max}
        for row in rows:
            if row["action_type"] != action_type:
                continue
            slots = int(row["argument_slots"])
            row["action_relative_complexity_band"] = "low" if slots <= low_max else "medium" if slots <= medium_max else "high"
    return thresholds


def seeded_rank(seed: int, identifier: str) -> str:
    return sha256_text(f"{seed}:{identifier}")


def greedy_select(candidates: list[dict[str, Any]], quota: int, seed: int, action_type: str) -> list[dict[str, Any]]:
    remaining = list(candidates)
    chosen: list[dict[str, Any]] = []
    used_complexity: Counter[str] = Counter()
    used_keys: Counter[str] = Counter()
    used_intents: Counter[str] = Counter()
    used_structures: Counter[str] = Counter()
    used_tools: Counter[str] = Counter()
    for _ in range(quota):
        def rank(row: dict[str, Any]):
            structural_priority = (
                12 * int(row["unique_tool_count"]) + 8 * int(row["step_count"]) + 6 * int(row["edge_count"])
                + 6 * int(row["artifact_reference_count"]) + int(row["argument_slots"])
            ) if action_type == "workflow" else int(row["argument_slots"])
            return (
                used_tools[row["tool_sequence_signature"]],
                used_complexity[row["action_relative_complexity_band"]],
                used_keys[row["argument_key_signature"]],
                used_intents[row["intent"]],
                used_structures[row["structural_signature"]],
                -structural_priority,
                seeded_rank(seed, row["id"]),
            )
        picked = min(remaining, key=rank)
        chosen.append(picked)
        used_tools[picked["tool_sequence_signature"]] += 1
        used_complexity[picked["action_relative_complexity_band"]] += 1
        used_keys[picked["argument_key_signature"]] += 1
        used_intents[picked["intent"]] += 1
        used_structures[picked["structural_signature"]] += 1
        remaining = [row for row in remaining if row["id"] != picked["id"]]
    return chosen


def run(config_path: Path, root: Path) -> int:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    source = root / cfg["train_source"]
    output = root / cfg["output"]
    allowed_attempt = output / "attempt0_missing_pytest"
    if output.exists() and any(path != allowed_attempt for path in output.iterdir()):
        raise RuntimeError("reward_design_v1 contains non-attempt artifacts; refusing overwrite")
    output.mkdir(parents=True, exist_ok=True)
    test_path = root / "hydro_remote_agent/tests/test_structural_contrast_reward_unittest.py"
    test_run = subprocess.run([sys.executable, "-m", "unittest", "hydro_remote_agent.tests.test_structural_contrast_reward_unittest", "-v"], cwd=root, capture_output=True, text=True, check=False)
    unit_report = {"status": "pass" if test_run.returncode == 0 else "fail", "returncode": test_run.returncode, "stdout": test_run.stdout, "stderr": test_run.stderr, "test_file": str(test_path.relative_to(root)), "test_file_sha256": sha256_file(test_path)}
    write_json(output / "UNIT_TEST_REPORT.json", unit_report)
    if test_run.returncode != 0:
        raise RuntimeError("Structural reward unit tests failed; generation forbidden")

    rows: list[dict[str, Any]] = []
    with source.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            record = json.loads(raw_line.decode("utf-8"))
            action_type = str(gold_action(record)["action"]["type"])
            if action_type in cfg["sampling"]["action_types"]:
                rows.append(structural_row(record, line_number, hashlib.sha256(raw_line).hexdigest(), cfg))
    complexity_thresholds = assign_complexity_bands(rows)
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[(row["action_type"], row["difficulty"])].append(row)
    selected: list[dict[str, Any]] = []
    quota = int(cfg["sampling"]["quota_per_action_difficulty_cell"])
    for action_type in cfg["sampling"]["action_types"]:
        for difficulty in ("easy", "medium", "hard"):
            candidates = buckets[(action_type, difficulty)]
            if len(candidates) < quota:
                raise RuntimeError(f"Insufficient rows for {action_type}/{difficulty}")
            selected.extend(greedy_select(candidates, quota, int(cfg["seed"]), action_type))
    if len(selected) != int(cfg["sampling"]["total_samples"]) or len({row["id"] for row in selected}) != len(selected):
        raise RuntimeError("Selection count/uniqueness failed")

    created_at = datetime.now(timezone.utc).isoformat()
    spec_a = {
        "schema_version": "vaguehydro.reward_spec.a.v1", "created_at": created_at, **cfg["reward_a"],
        "invalid_handling": "GoldActionReward returns all-zero breakdown for invalid candidates",
        "canonicalizer": "hydro_remote_agent.rewards.request_canonicalizer.canonicalize_agent_request",
        "paired_role": "frozen baseline; never replaced or relabeled by reward B",
    }
    spec_b = {
        "schema_version": "vaguehydro.reward_spec.b.v1", "created_at": created_at, **cfg["reward_b"],
        "components": list(B_COMPONENTS), "weights_by_gold_action_type": WEIGHTS_BY_ACTION,
        "component_semantics": {
            "schema": "strict AgentRequest validity; invalid hard zero", "action": "exact action type",
            "intent": "exact canonical intent", "expected_output": "aligned exact structured fields",
            "tool_set": "set F1 over registered tool names", "argument_keys": "set F1 over (tool-or-step, key)",
            "argument_values": "aligned exact canonical JSON value average", "workflow_nodes": "set F1 over (step_id, tool)",
            "workflow_edges": "set F1 over dependency edges", "artifact_references": "set F1 over consumer/producer/artifact triples",
            "verification": "set F1 over owner/policy pairs", "stop": "aligned exact structured stop fields",
        },
        "anti_signal_hacking": ["no request_id reward", "no arbitrary string similarity", "no model-output-derived targets", "no candidate-batch normalization in total reward"],
    }
    spec_a_path = output / "REWARD_SPEC_A.json"
    spec_b_path = output / "REWARD_SPEC_B.json"
    write_json(spec_a_path, spec_a)
    write_json(spec_b_path, spec_b)
    plan = {
        "schema_version": "vaguehydro.reward_design.preregistration.v1", "created_at": created_at,
        "state": "FROZEN_BEFORE_GENERATION", "config": cfg, "config_sha256": sha256_file(config_path),
        "reward_spec_a_sha256": sha256_file(spec_a_path), "reward_spec_b_sha256": sha256_file(spec_b_path),
        "reward_b_code_sha256": sha256_file(root / "hydro_remote_agent/rewards/structural_contrast_reward.py"),
        "unit_test_report_sha256": sha256_file(output / "UNIT_TEST_REPORT.json"),
        "curriculum_c": {**cfg["curriculum_c"], "action_relative_complexity_thresholds": complexity_thresholds},
        "gates": cfg["preregistered_gates"],
        "immutable_after_generation_starts": ["A implementation/weights", "B implementation/weights", "C selection", "sample IDs/rows", "G", "seed", "temperature/top_p", "length budgets", "all gates"],
        "forbidden_sources": ["frozen_test", "gold_240", "validation", "model outputs for selection", "A or B reward values for selection"],
        "pre_generation_attempts": [{"name": "attempt0_missing_pytest", "scientific_generation_started": False, "reason": "remote environment lacks optional pytest package"}] if allowed_attempt.is_dir() else [],
    }
    plan_path = output / "PRE_REGISTERED_PLAN.json"
    write_json(plan_path, plan)
    manifest_records = []
    for index, row in enumerate(selected):
        item = dict(row)
        item["manifest_index"] = index
        item["generation_seed"] = int(cfg["seed"]) + index
        item["max_new_tokens"] = int(cfg["sampling"]["max_new_tokens"][row["action_type"]])
        manifest_records.append(item)
    manifest = {
        "schema_version": "vaguehydro.reward_design.data_manifest.v1", "created_at": created_at,
        "state": "FROZEN_BEFORE_GENERATION", "source": {"path": cfg["train_source"], "split": "M1_train_only", "bytes": source.stat().st_size, "sha256": sha256_file(source)},
        "record_count": len(manifest_records), "group_size": int(cfg["sampling"]["group_size"]),
        "expected_candidate_count": len(manifest_records) * int(cfg["sampling"]["group_size"]), "records": manifest_records,
        "selected_distribution": {
            "action_type": dict(sorted(Counter(row["action_type"] for row in manifest_records).items())),
            "difficulty": dict(sorted(Counter(row["difficulty"] for row in manifest_records).items())),
            "action_x_difficulty": dict(sorted(Counter(f"{row['action_type']}|{row['difficulty']}" for row in manifest_records).items())),
            "complexity_band": dict(sorted(Counter(row["action_relative_complexity_band"] for row in manifest_records).items())),
            "tool_sequence": dict(sorted(Counter(row["tool_sequence_signature"] for row in manifest_records).items())),
            "step_count": dict(sorted(Counter(str(row["step_count"]) for row in manifest_records).items())),
            "edge_count": dict(sorted(Counter(str(row["edge_count"]) for row in manifest_records).items())),
            "artifact_reference_count": dict(sorted(Counter(str(row["artifact_reference_count"]) for row in manifest_records).items())),
            "language": dict(sorted(Counter(row["language"] for row in manifest_records).items())),
        },
        "selection_used_model_outputs": False, "selection_used_reward_a": False, "selection_used_reward_b": False,
        "frozen_test_reads": 0, "posthoc_changes": 0,
    }
    manifest_path = output / "DATA_MANIFEST.json"
    write_json(manifest_path, manifest)
    lock = {
        "state": "LOCKED_BEFORE_GENERATION", "created_at": created_at, "generation_started": False,
        "config_sha256": sha256_file(config_path), "source_sha256": sha256_file(source),
        "pre_registered_plan_sha256": sha256_file(plan_path), "reward_spec_a_sha256": sha256_file(spec_a_path),
        "reward_spec_b_sha256": sha256_file(spec_b_path), "data_manifest_sha256": sha256_file(manifest_path),
        "reward_b_code_sha256": sha256_file(root / "hydro_remote_agent/rewards/structural_contrast_reward.py"),
        "reward_b_test_sha256": sha256_file(test_path), "unit_test_report_sha256": sha256_file(output / "UNIT_TEST_REPORT.json"),
    }
    write_json(output / "PREREGISTRATION_LOCK.json", lock)
    print(json.dumps({"status": "locked", "samples": len(manifest_records), "unit_tests": unit_report["status"], "output": str(output)}, ensure_ascii=False))
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
