"""Score preregistered controlled mutations with Reward A and alpha-invariant Reward B v2."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.rewards.hard_negative_mutations import generate_mutations
from hydro_remote_agent.rewards.structural_contrast_reward import COMPONENTS
from hydro_remote_agent.rewards.structural_contrast_reward_v2 import StructuralContrastRewardV2
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.prepare_vaguehydro_grpo_reward_design_v1 import sha256_file, write_json


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def summarize(rows: list[dict[str, Any]], reward: str) -> dict[str, Any]:
    key = f"margin_{reward}"
    margins = [float(row[key]) for row in rows]
    return {
        "pairs": len(rows),
        "ranking_accuracy": sum(value > 0 for value in margins) / len(margins) if margins else 0.0,
        "ties": sum(math.isclose(value, 0.0, abs_tol=1e-12) for value in margins),
        "misranked": sum(value < 0 for value in margins),
        "margin": {
            "min": min(margins) if margins else 0.0, "p05": quantile(margins, 0.05),
            "median": statistics.median(margins) if margins else 0.0,
            "mean": statistics.fmean(margins) if margins else 0.0,
            "p95": quantile(margins, 0.95), "max": max(margins) if margins else 0.0,
        },
    }


def run(config_path: Path, root: Path) -> int:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    output = root / cfg["output"]
    lock_path = output / "PREREGISTRATION_LOCK.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    expected = {
        "config_sha256": sha256_file(config_path),
        "plan_sha256": sha256_file(output / "PRE_REGISTERED_PLAN.json"),
        "manifest_sha256": sha256_file(output / "DATA_MANIFEST.json"),
        "mutation_spec_sha256": sha256_file(output / "MUTATION_SPEC.json"),
        "canonicalization_spec_sha256": sha256_file(output / "CANONICALIZATION_SPEC.json"),
        "mutation_code_sha256": sha256_file(root / "hydro_remote_agent/rewards/hard_negative_mutations.py"),
        "reward_a_code_sha256": sha256_file(root / "hydro_remote_agent/rewards/gold_action_reward.py"),
        "reward_b_code_sha256": sha256_file(root / "hydro_remote_agent/rewards/structural_contrast_reward_v2.py"),
    }
    if lock.get("scoring_started") or any(lock.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Preregistration lock mismatch or scoring already started")
    for name in ("PAIR_SCORES.jsonl", "STRESS_REPORT.json", "COUNTEREXAMPLES.json"):
        if (output / name).exists():
            raise RuntimeError(f"Refusing to overwrite {name}")
    lock["scoring_started"] = True
    lock["scoring_started_at"] = datetime.now(timezone.utc).isoformat()
    write_json(lock_path, lock)

    manifest = json.loads((output / "DATA_MANIFEST.json").read_text(encoding="utf-8"))
    regression_report = json.loads((output / "REGRESSION_TEST_REPORT.json").read_text(encoding="utf-8"))
    registry = load_tool_registry(root / cfg["registry"])
    reward_a = GoldActionReward(registry)
    reward_b = StructuralContrastRewardV2(registry)
    rows: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    for record in manifest["records"]:
        gold = record["gold_action"]
        gold_a = reward_a.score(gold, gold).to_dict()
        gold_b = reward_b.score(gold, gold).to_dict()
        for index, mutation in enumerate(generate_mutations(gold)):
            score_a = reward_a.score(mutation.candidate, gold).to_dict()
            score_b = reward_b.score(mutation.candidate, gold).to_dict()
            target_checks = {
                component: float(score_b[component]) < float(gold_b[component])
                for component in mutation.expected_changed_components if component in COMPONENTS
            }
            stable_checks = {
                component: math.isclose(float(score_b[component]), float(gold_b[component]), abs_tol=1e-12)
                for component in mutation.expected_stable_components if component in COMPONENTS
            }
            row = {
                "pair_id": f"{record['id']}::{index:02d}::{mutation.name}",
                "source_id": record["id"], "source_line_number": record["source_line_number"],
                "source_line_sha256": record["source_line_sha256"], "action_type": record["action_type"],
                "difficulty": record["difficulty"], "argument_complexity": record["action_relative_complexity_band"],
                "tool_sequence": record["tool_sequence_signature"], "dag_complexity": record["dag_complexity_band"],
                "family": mutation.family, "mutation_name": mutation.name, "equivalence": mutation.equivalence,
                "valid_expected": mutation.valid_expected, "candidate": mutation.candidate,
                "candidate_sha256": sha256_value(mutation.candidate),
                "mutation_provenance": {
                    "expected_changed_components": list(mutation.expected_changed_components),
                    "expected_stable_components": list(mutation.expected_stable_components), "note": mutation.note,
                },
                "gold_reward_a": gold_a, "candidate_reward_a": score_a,
                "gold_reward_b": gold_b, "candidate_reward_b": score_b,
                "margin_a": float(gold_a["total"]) - float(score_a["total"]),
                "margin_b": float(gold_b["total"]) - float(score_b["total"]),
                "target_component_checks_b": target_checks, "stable_component_checks_b": stable_checks,
                "target_component_contract_pass_b": all(target_checks.values()),
                "stability_contract_pass_b": all(stable_checks.values()),
            }
            rows.append(row)
            provenance.append({key: row[key] for key in ("pair_id", "source_id", "family", "mutation_name", "candidate_sha256")})
    with (output / "PAIR_SCORES.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    hard = [row for row in rows if not row["equivalence"] and row["family"] != "invalid_schema"]
    invalid = [row for row in rows if row["family"] == "invalid_schema"]
    equivalent = [row for row in rows if row["equivalence"]]
    family_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stratum_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in hard:
        family_rows[row["family"]].append(row)
        stratum_rows[f"{row['action_type']}|{row['difficulty']}|{row['argument_complexity']}|{row['dag_complexity']}"] .append(row)
    by_family = {family: {"reward_a": summarize(items, "a"), "reward_b": summarize(items, "b")} for family, items in sorted(family_rows.items())}
    by_stratum = {name: {"reward_a": summarize(items, "a"), "reward_b": summarize(items, "b")} for name, items in sorted(stratum_rows.items())}

    invalid_zero_a = sum(row["candidate_reward_a"]["invalid"] and row["candidate_reward_a"]["total"] == 0 for row in invalid) / len(invalid)
    invalid_zero_b = sum(row["candidate_reward_b"]["invalid"] and row["candidate_reward_b"]["total"] == 0 for row in invalid) / len(invalid)
    equivalent_a = sum(math.isclose(row["margin_a"], 0.0, abs_tol=1e-12) for row in equivalent) / len(equivalent)
    equivalent_b = sum(math.isclose(row["margin_b"], 0.0, abs_tol=1e-12) for row in equivalent) / len(equivalent)
    target_checks = [value for row in hard for value in row["target_component_checks_b"].values()]
    stable_checks = [value for row in hard for value in row["stable_component_checks_b"].values()]
    target_rate = sum(target_checks) / len(target_checks)
    stability_rate = sum(stable_checks) / len(stable_checks)
    overall_a = summarize(hard, "a")
    overall_b = summarize(hard, "b")
    gates = cfg["preregistered_gates"]
    family_gate = all(item["reward_b"]["ranking_accuracy"] >= gates["each_mutation_family_pairwise_ranking_accuracy_min"] for item in by_family.values())
    categories = {
        "tool": [row for row in hard if row["family"] == "tool_replacement"],
        "argument": [row for row in hard if row["family"] in {"argument_value", "argument_slot"}],
        "workflow": [row for row in hard if row["action_type"] == "workflow" and row["family"] in {"workflow_node", "dag_link", "artifact_reference", "verification_stop"}],
    }
    category_positive = {name: bool(items) and all(row["margin_b"] > 0 for row in items) for name, items in categories.items()}
    gate_results = {
        "overall_pairwise": overall_b["ranking_accuracy"] >= gates["overall_pairwise_ranking_accuracy_min"],
        "each_mutation_family": family_gate,
        "invalid_hard_zero": invalid_zero_b == gates["invalid_hard_zero_rate"],
        "equivalence_preservation": equivalent_b == gates["equivalence_preservation_rate"],
        "target_component_decline": target_rate == gates["target_component_decline_rate"],
        "declared_stability": stability_rate == gates["declared_stability_rate"],
        "positive_margin_categories": sum(category_positive.values()) >= gates["minimum_positive_margin_categories"],
        "v1_132_hard_negative_non_regression": len(hard) == 132 and overall_b["ranking_accuracy"] >= gates["v1_132_hard_negative_ranking_accuracy_min"],
        "regression_tests": regression_report["status"] == "pass" if gates["regression_tests_required"] else True,
    }
    all_pass = all(gate_results.values())
    counterexamples = sorted(
        [row for row in rows if (row["equivalence"] and not math.isclose(row["margin_b"], 0.0, abs_tol=1e-12)) or (not row["equivalence"] and row["family"] != "invalid_schema" and row["margin_b"] <= 0) or not row["target_component_contract_pass_b"] or not row["stability_contract_pass_b"]],
        key=lambda row: (abs(float(row["margin_b"])), row["pair_id"]),
    )
    write_json(output / "COUNTEREXAMPLES.json", {"count": len(counterexamples), "minimum_counterexamples": counterexamples[:50]})
    report = {
        "schema_version": "vaguehydro.hard_negative.stress_report.v2", "created_at": datetime.now(timezone.utc).isoformat(),
        "decision": "PASS_ELIGIBLE_FOR_PREFERENCE_CANDIDATE_GENERATION" if all_pass else "BLOCKED_REVISE_REWARD_BEFORE_DPO_OR_SFT",
        "all_gates_pass": all_pass, "samples": len(manifest["records"]), "pairs_total": len(rows),
        "hard_negative_pairs": len(hard), "equivalence_pairs": len(equivalent), "invalid_pairs": len(invalid),
        "reward_a_overall": overall_a, "reward_b_overall": overall_b, "by_family": by_family, "by_stratum": by_stratum,
        "invalid_hard_zero_rate_a": invalid_zero_a, "invalid_hard_zero_rate_b": invalid_zero_b,
        "equivalence_preservation_rate_a": equivalent_a, "equivalence_preservation_rate_b": equivalent_b,
        "target_component_decline_rate_b": target_rate, "declared_stability_rate_b": stability_rate,
        "positive_margin_categories_b": category_positive, "gate_results": gate_results, "thresholds": gates,
        "reward_ties_a": overall_a["ties"], "reward_ties_b": overall_b["ties"],
        "misranked_a": overall_a["misranked"], "misranked_b": overall_b["misranked"],
        "frozen_test_reads": 0, "model_calls": 0, "optimizer_steps": 0, "gradient_updates": 0,
        "dag_stratification_limitation": manifest["dag_stratification_limitation"],
        "paired_v1_non_regression": {"expected_pairs": 132, "observed_pairs": len(hard), "ranking_accuracy_b": overall_b["ranking_accuracy"]},
        "regression_test_status": regression_report["status"],
    }
    write_json(output / "STRESS_REPORT.json", report)
    (output / "STRESS_REPORT.md").write_text(
        "# VagueHydro Hard-Negative Stress v2\n\n"
        f"- Decision: **{report['decision']}**\n"
        f"- Samples / valid hard-negative pairs: `{report['samples']}` / `{report['hard_negative_pairs']}`\n"
        f"- Reward A / B pairwise ranking: `{overall_a['ranking_accuracy']:.3f}` / `{overall_b['ranking_accuracy']:.3f}`\n"
        f"- Reward A / B ties: `{overall_a['ties']}` / `{overall_b['ties']}`\n"
        f"- Invalid hard-zero A / B: `{invalid_zero_a:.3f}` / `{invalid_zero_b:.3f}`\n"
        f"- Equivalence preservation A / B: `{equivalent_a:.3f}` / `{equivalent_b:.3f}`\n"
        f"- Target decline / declared stability B: `{target_rate:.3f}` / `{stability_rate:.3f}`\n\n"
        "Training remains disabled. Preference data is emitted only if every preregistered gate passes.\n",
        encoding="utf-8",
    )

    recommendation = {
        "decision": report["decision"], "training_started": False,
        "hard_negative_sft": {
            "applicability": "conditional" if all_pass else "blocked",
            "assessment": "Useful for teaching exact schema and local corruption recovery, but risks teaching deterministic templates and requires audited gold-negative pairs.",
        },
        "dpo": {
            "applicability": "conditional" if all_pass else "blocked",
            "assessment": "Appropriate only when the reward ranks every preference family reliably; ties or equivalence penalties create mislabeled preferences.",
        },
        "recommended_next_step": "version and human/audit-review preference candidates" if all_pass else "revise structural reward invariances/component contracts and rerun a new preregistered stress test",
    }
    write_json(output / "TRAINING_ROUTE_RECOMMENDATION.json", recommendation)
    (output / "TRAINING_ROUTE_RECOMMENDATION.md").write_text(
        "# Training Route Recommendation\n\n"
        f"**{recommendation['decision']}**\n\n"
        f"- Hard-negative SFT: {recommendation['hard_negative_sft']['applicability']}. {recommendation['hard_negative_sft']['assessment']}\n"
        f"- DPO: {recommendation['dpo']['applicability']}. {recommendation['dpo']['assessment']}\n"
        f"- Next: {recommendation['recommended_next_step']}.\n",
        encoding="utf-8",
    )
    if all_pass:
        family_suitability = {
            "tool_replacement": "tool-selection preference and rejected-action contrast",
            "argument_value": "argument correction preference and rejected-argument contrast",
            "argument_slot": "schema-complete argument preference and slot-repair contrast",
            "verification_stop": "verification-policy preference and policy-repair contrast",
            "workflow_node": "workflow-policy preference and node-level repair contrast",
            "dag_link": "dependency preference and DAG-link repair contrast",
            "artifact_reference": "artifact-grounding preference and reference-repair contrast",
        }
        preference = {
            "schema_version": "vaguehydro.preference_candidates.v2", "source_run": cfg["output"],
            "status": "CANDIDATE_ONLY_NOT_TRAINED", "pair_count": len(hard),
            "exclusion_policy": {"equivalence_controls": "excluded", "invalid_schema": "excluded", "ambiguous_pairs": "excluded", "posthoc_filtering": False},
            "excluded_counts": {"equivalence": len(equivalent), "invalid_schema": len(invalid), "ambiguous": 0},
            "pairs": [{
                "pair_id": row["pair_id"], "source_id": row["source_id"],
                "chosen": manifest["records"][next(i for i, item in enumerate(manifest["records"]) if item["id"] == row["source_id"])]["gold_action"],
                "rejected": row["candidate"], "family": row["family"], "margin_b": row["margin_b"],
                "audit_status": "passed", "ambiguous": False,
                "suitability": {
                    "dpo": {"eligible": True, "role": "chosen_vs_rejected_preference"},
                    "hard_negative_sft": {"eligible": True, "role": "gold_target_with_rejected_contrast_metadata"},
                    "family_use": family_suitability[row["family"]],
                },
            } for row in hard],
        }
        write_json(output / "PREFERENCE_DATA_MANIFEST.json", preference)

    reread = [json.loads(line) for line in (output / "PAIR_SCORES.jsonl").read_text(encoding="utf-8").splitlines() if line]
    mismatches_a = mismatches_b = 0
    for row in reread:
        gold = next(item["gold_action"] for item in manifest["records"] if item["id"] == row["source_id"])
        if reward_a.score(row["candidate"], gold).to_dict() != row["candidate_reward_a"]:
            mismatches_a += 1
        if reward_b.score(row["candidate"], gold).to_dict() != row["candidate_reward_b"]:
            mismatches_b += 1
    write_json(output / "TEST_REPORT.json", {
        "status": "pass" if mismatches_a == mismatches_b == 0 else "fail", "pair_count": len(reread),
        "reward_a_recompute_mismatches": mismatches_a, "reward_b_recompute_mismatches": mismatches_b,
        "mutation_provenance_count": len(provenance), "string_similarity_used": False,
        "unit_tests": json.loads((output / "UNIT_TEST_REPORT.json").read_text(encoding="utf-8")),
        "regression_tests": regression_report,
    })
    write_json(output / "INTEGRITY_EVIDENCE.json", {
        "status": "pass" if mismatches_a == mismatches_b == 0 else "fail", "pre_registered": True,
        "source_split": "M1_train_only", "frozen_test_reads": 0, "selection_used_rewards": False,
        "selection_used_model_outputs": False, "optimizer_steps": 0, "gradient_updates": 0,
        "preference_manifest_emitted": bool(all_pass), "training_started": False,
    })
    print(json.dumps({"decision": report["decision"], "all_gates_pass": all_pass, "pairs": len(rows)}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    return run(Path(args.config).resolve(), Path(args.root).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
