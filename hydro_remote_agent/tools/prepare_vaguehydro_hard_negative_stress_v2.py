"""Freeze v2 alpha-invariant reward stress test before scoring."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hydro_remote_agent.rewards.hard_negative_mutations import generate_mutations
from hydro_remote_agent.tools.prepare_vaguehydro_grpo_reward_design_v1 import (
    assign_complexity_bands,
    greedy_select,
    sha256_file,
    structural_row,
    write_json,
)
from hydro_remote_agent.tools.train_vaguehydro_r_m2_grpo_smoke import gold_action


def run(config_path: Path, root: Path) -> int:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    output = root / cfg["output"]
    source = root / cfg["train_source"]
    preserved_attempt = output / "attempt0_position_based_canonicalizer_insufficient"
    stability_attempt = output / "attempt1_graph_minimum_relabels_nodes_on_edge_mutation"
    allowed_attempts = {preserved_attempt, stability_attempt}
    if output.exists() and any(path not in allowed_attempts for path in output.iterdir()):
        raise RuntimeError(f"Refusing to overwrite existing run: {output}")
    output.mkdir(parents=True, exist_ok=True)
    if sha256_file(source) != cfg["expected_train_source_sha256"]:
        raise RuntimeError("M1 train source SHA256 mismatch")

    test_file = root / "hydro_remote_agent/tests/test_structural_contrast_reward_v2_unittest.py"
    test = subprocess.run(
        [sys.executable, "-m", "unittest", "hydro_remote_agent.tests.test_structural_contrast_reward_v2_unittest", "-v"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    unit_report = {
        "status": "pass" if test.returncode == 0 else "fail", "returncode": test.returncode,
        "stdout": test.stdout, "stderr": test.stderr,
        "test_file": str(test_file.relative_to(root)), "test_file_sha256": sha256_file(test_file),
    }
    write_json(output / "UNIT_TEST_REPORT.json", unit_report)
    write_json(output / "REGRESSION_TEST_REPORT.json", unit_report)
    if test.returncode:
        raise RuntimeError("Mutation unit tests failed before preregistration")

    rows: list[dict[str, Any]] = []
    with source.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            record = json.loads(raw_line.decode("utf-8"))
            if gold_action(record)["action"]["type"] in cfg["sampling"]["action_types"]:
                row = structural_row(record, line_number, hashlib.sha256(raw_line).hexdigest(), cfg)
                row["dag_complexity_band"] = f"nodes_{row['step_count']}_edges_{row['edge_count']}"
                rows.append(row)
    thresholds = assign_complexity_bands(rows)
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[(row["action_type"], row["difficulty"])].append(row)
    selected: list[dict[str, Any]] = []
    quota = int(cfg["sampling"]["quota_per_action_difficulty_cell"])
    for action_type in cfg["sampling"]["action_types"]:
        for difficulty in ("easy", "medium", "hard"):
            selected.extend(greedy_select(buckets[(action_type, difficulty)], quota, int(cfg["seed"]), action_type))
    if len(selected) != int(cfg["sampling"]["total_samples"]):
        raise RuntimeError("Unexpected selected sample count")
    v1_manifest = json.loads((root / "runs/hydro_remote_agent/vaguehydro_hard_negative_stress_v1/DATA_MANIFEST.json").read_text(encoding="utf-8"))
    v1_signature = [(row["id"], row["source_line_sha256"], row["gold_action_sha256"]) for row in v1_manifest["records"]]
    v2_signature = [(row["id"], row["source_line_sha256"], row["gold_action_sha256"]) for row in selected]
    if v1_signature != v2_signature:
        raise RuntimeError("v2 sample/source/gold signature differs from frozen v1")

    created_at = datetime.now(timezone.utc).isoformat()
    mutation_spec = {
        "schema_version": "vaguehydro.hard_negative.mutation_spec.v1",
        "created_at": created_at,
        "generator": "hydro_remote_agent.rewards.hard_negative_mutations.generate_mutations",
        "generator_sha256": sha256_file(root / "hydro_remote_agent/rewards/hard_negative_mutations.py"),
        "families": cfg["mutation_families"],
        "equivalence_controls": cfg["equivalence_controls"],
        "single_factor_policy": "one semantic concept per mutation; schema-coupled DAG edge and artifact path form one atomic dag_link mutation",
        "applicability": {
            "tool_call": ["tool_replacement", "argument_value", "argument_slot", "verification_stop", "invalid_schema"],
            "workflow": ["tool_replacement", "argument_value", "argument_slot", "workflow_node", "dag_link", "artifact_reference", "verification_stop", "invalid_schema"],
            "stop": "No terminal actions are sampled by design; verification_stop uses verification policy for tool/workflow actions.",
        },
        "mutation_provenance_required": ["source_id", "family", "name", "candidate_sha256", "expected_changed_components", "expected_stable_components", "valid_expected", "equivalence"],
        "forbidden": ["string similarity", "embedding similarity", "model-generated targets", "reward-based mutation selection", "posthoc sample deletion"],
    }
    write_json(output / "MUTATION_SPEC.json", mutation_spec)
    canonicalization_spec = {
        "schema_version": "vaguehydro.workflow_canonicalization.v2",
        "created_at": created_at,
        "implementation": "hydro_remote_agent/rewards/structural_contrast_reward_v2.py",
        "implementation_sha256": sha256_file(root / "hydro_remote_agent/rewards/structural_contrast_reward_v2.py"),
        "algorithm": [
            "validate unique workflow node IDs and the original earlier-step dependency contract",
            "build intrinsic exact semantic labels from tool, arguments, verification, artifact names, and declared structured reference fields",
            "assign stable canonical IDs by intrinsic label and use exhaustive graph encoding only to disambiguate exact-label ties",
            "rewrite exact depends_on, artifact, argument, verification-owner/target, and stop reference fields",
            "canonicalize gold independently, then align candidate nodes to gold IDs by minimum exact structured semantic plus graph edit cost",
            "break equal-cost mappings by lexicographically minimal normalized JSON encoding",
        ],
        "semantic_labels": ["tool", "arguments", "verification policy", "dependency set", "artifact name and producer", "structured owner/target references"],
        "exact_reference_policy": "full structured reference patterns and declared *_step_id fields only; no substring, edit-distance, token, or embedding similarity",
        "ambiguity_handling": "exact-label automorphisms and equal-cost candidate alignments are resolved by lexicographically minimal normalized encoding; no ambiguous pair is emitted for preference data",
        "invalid_handling": "duplicate/missing IDs, undefined dependencies, non-topological/cyclic input, or search-budget excess fail closed and receive invalid hard-zero",
        "budgets": {"max_workflow_nodes": 8, "max_topological_orders": 100000},
        "current_schema_note": "workflow verification owner is the canonical node ID; current AgentRequest has no workflow stop object, but exact structured stop/verification target reference fields are rewritten for schema-compatible extensions and regression-tested at helper level",
        "forbidden": ["string similarity", "embedding similarity", "dropping nodes", "dropping edges", "ignoring artifact identity", "repairing invalid references"],
    }
    write_json(output / "CANONICALIZATION_SPEC.json", canonicalization_spec)
    records = []
    for index, row in enumerate(selected):
        item = dict(row)
        item["manifest_index"] = index
        item["mutation_seed"] = int(cfg["seed"]) + index
        item["planned_mutations"] = [
            {key: value for key, value in mutation.to_dict().items() if key != "candidate"}
            for mutation in generate_mutations(item["gold_action"])
        ]
        records.append(item)
    distribution_fields = {
        "action_type": Counter(row["action_type"] for row in records),
        "difficulty": Counter(row["difficulty"] for row in records),
        "argument_complexity": Counter(row["action_relative_complexity_band"] for row in records),
        "tool_sequence": Counter(row["tool_sequence_signature"] for row in records),
        "dag_complexity": Counter(row["dag_complexity_band"] for row in records),
    }
    manifest = {
        "schema_version": "vaguehydro.hard_negative.data_manifest.v1", "created_at": created_at,
        "state": "FROZEN_BEFORE_SCORING", "seed": cfg["seed"], "record_count": len(records),
        "source": {"path": cfg["train_source"], "split": "M1_train_only", "bytes": source.stat().st_size, "sha256": sha256_file(source)},
        "records": records, "selected_distribution": {key: dict(sorted(value.items())) for key, value in distribution_fields.items()},
        "selection_used_rewards": False, "selection_used_model_outputs": False, "frozen_test_reads": 0,
        "paired_with_v1": {"same_ids_source_lines_and_gold_actions": True, "v1_record_count": len(v1_signature)},
        "dag_stratification_limitation": "All 6544 M1 workflow rows have exactly 2 nodes and 1 edge; only the observed nodes_2_edges_1 stratum exists.",
    }
    write_json(output / "DATA_MANIFEST.json", manifest)
    plan = {
        "schema_version": "vaguehydro.hard_negative.preregistration.v1", "created_at": created_at,
        "state": "FROZEN_BEFORE_SCORING", "config": cfg, "config_sha256": sha256_file(config_path),
        "data_manifest_sha256": sha256_file(output / "DATA_MANIFEST.json"),
        "mutation_spec_sha256": sha256_file(output / "MUTATION_SPEC.json"),
        "canonicalization_spec_sha256": sha256_file(output / "CANONICALIZATION_SPEC.json"),
        "reward_a_code_sha256": sha256_file(root / "hydro_remote_agent/rewards/gold_action_reward.py"),
        "reward_b_code_sha256": sha256_file(root / "hydro_remote_agent/rewards/structural_contrast_reward_v2.py"),
        "parent_run": cfg["parent_run"], "single_declared_repair": cfg["single_declared_repair"],
        "unit_test_report_sha256": sha256_file(output / "UNIT_TEST_REPORT.json"),
        "regression_test_report_sha256": sha256_file(output / "REGRESSION_TEST_REPORT.json"),
        "argument_complexity_thresholds": thresholds, "gates": cfg["preregistered_gates"],
        "immutable_after_scoring_starts": ["sample IDs/rows", "mutation generator/spec", "reward A/B code", "all gates", "seed"],
        "forbidden_sources": ["frozen_test", "gold_240", "validation", "reward values", "model outputs"],
        "pre_generation_attempts": ([{
            "name": "attempt0_position_based_canonicalizer_insufficient",
            "scientific_scoring_completed": True,
            "reason": "position-based normalization did not establish invariance to alternate valid branch-DAG topological orderings",
            "claim_withdrawn": True,
        }] if preserved_attempt.is_dir() else []) + ([{
            "name": "attempt1_graph_minimum_relabels_nodes_on_edge_mutation",
            "scientific_scoring_completed": True,
            "reason": "independent minimum graph encoding passed equivalence but relabeled unchanged nodes after edge removal; declared stability was 0.9875",
            "unchanged_for_retry": ["sample IDs", "candidate payloads", "reward weights", "gates", "seed"],
        }] if stability_attempt.is_dir() else []),
    }
    write_json(output / "PRE_REGISTERED_PLAN.json", plan)
    lock = {
        "schema_version": "vaguehydro.hard_negative.lock.v1", "state": "LOCKED_BEFORE_SCORING",
        "created_at": created_at, "scoring_started": False,
        "config_sha256": sha256_file(config_path), "plan_sha256": sha256_file(output / "PRE_REGISTERED_PLAN.json"),
        "manifest_sha256": sha256_file(output / "DATA_MANIFEST.json"), "mutation_spec_sha256": sha256_file(output / "MUTATION_SPEC.json"),
        "canonicalization_spec_sha256": sha256_file(output / "CANONICALIZATION_SPEC.json"),
        "mutation_code_sha256": sha256_file(root / "hydro_remote_agent/rewards/hard_negative_mutations.py"),
        "reward_a_code_sha256": sha256_file(root / "hydro_remote_agent/rewards/gold_action_reward.py"),
        "reward_b_code_sha256": sha256_file(root / "hydro_remote_agent/rewards/structural_contrast_reward_v2.py"),
    }
    write_json(output / "PREREGISTRATION_LOCK.json", lock)
    print(json.dumps({"status": "locked", "samples": len(records), "output": str(output)}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    return run(Path(args.config).resolve(), Path(args.root).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
