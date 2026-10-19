from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from hydro_remote_agent.rewards.hard_negative_mutations import generate_mutations
from hydro_remote_agent.rewards.structural_contrast_reward_v2 import (
    StructuralContrastRewardV2,
    canonicalize_workflow_graph,
    rewrite_step_references,
)
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


ROOT = Path(__file__).resolve().parents[2]


def _branch_workflow() -> dict:
    point_path = "/tmp/points.xyz"
    return {
        "schema_version": "1.0", "request_id": "branch-test", "intent": "quality_branch",
        "action": {"type": "workflow", "steps": [
            {
                "step_id": "segment", "tool": "point_semantic_segmentation", "depends_on": [],
                "arguments": {"point_cloud_path": point_path, "return_probabilities": True},
                "verification": "skip",
            },
            {
                "step_id": "check_labels", "tool": "result_quality_verification", "depends_on": ["segment"],
                "arguments": {"result_path": "${segment.artifacts.point_labels}", "source_tool": "point_semantic_segmentation"},
                "verification": "skip",
            },
            {
                "step_id": "check_probs", "tool": "result_quality_verification", "depends_on": ["segment"],
                "arguments": {"result_path": "${segment.artifacts.class_probabilities}", "source_tool": "point_semantic_segmentation"},
                "verification": "skip",
            },
        ]},
    }


def _rename_and_reorder_branch(value: dict) -> dict:
    candidate = copy.deepcopy(value)
    rename = {"segment": "root_x", "check_labels": "left_x", "check_probs": "right_x"}
    steps = []
    for index in (0, 2, 1):
        step = rewrite_step_references(candidate["action"]["steps"][index], rename)
        step["step_id"] = rename[step["step_id"]]
        steps.append(step)
    candidate["action"]["steps"] = steps
    return candidate


class StructuralContrastRewardV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reward = StructuralContrastRewardV2(load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml"))
        manifest = json.loads((ROOT / "runs/hydro_remote_agent/vaguehydro_hard_negative_stress_v1/DATA_MANIFEST.json").read_text(encoding="utf-8"))
        cls.golds = [item["gold_action"] for item in manifest["records"]]
        cls.workflow_golds = [item["gold_action"] for item in manifest["records"] if item["action_type"] == "workflow"]

    def test_v1_twelve_alpha_rename_counterexamples_regress(self) -> None:
        controls = []
        for gold in self.workflow_golds:
            controls.extend(item for item in generate_mutations(gold) if item.name == "workflow_step_id_alpha_rename")
        self.assertEqual(len(controls), 12)
        for gold, control in zip(self.workflow_golds, controls):
            self.assertAlmostEqual(self.reward.score(control.candidate, gold).total, 1.0, places=12)

    def test_all_v1_equivalence_controls_preserved(self) -> None:
        for gold in self.golds:
            gold_total = self.reward.score(gold, gold).total
            for mutation in generate_mutations(gold):
                if mutation.equivalence:
                    self.assertAlmostEqual(self.reward.score(mutation.candidate, gold).total, gold_total, places=12, msg=mutation.name)

    def test_v1_132_hard_negatives_do_not_regress(self) -> None:
        count = 0
        for gold in self.golds:
            gold_total = self.reward.score(gold, gold).total
            for mutation in generate_mutations(gold):
                if not mutation.equivalence and mutation.family != "invalid_schema":
                    count += 1
                    self.assertLess(self.reward.score(mutation.candidate, gold).total, gold_total, mutation.name)
        self.assertEqual(count, 132)

    def test_v1_declared_component_contracts_do_not_regress(self) -> None:
        for gold in self.golds:
            gold_score = self.reward.score(gold, gold).to_dict()
            for mutation in generate_mutations(gold):
                if mutation.equivalence or mutation.family == "invalid_schema":
                    continue
                score = self.reward.score(mutation.candidate, gold).to_dict()
                for component in mutation.expected_changed_components:
                    self.assertLess(score[component], gold_score[component], f"{mutation.name}:{component}")
                for component in mutation.expected_stable_components:
                    self.assertAlmostEqual(score[component], gold_score[component], places=12, msg=f"{mutation.name}:{component}")

    def test_branch_alpha_rename_and_topological_order_are_equivalent(self) -> None:
        gold = _branch_workflow()
        candidate = _rename_and_reorder_branch(gold)
        score = self.reward.score(candidate, gold)
        self.assertAlmostEqual(score.total, 1.0, places=12)
        normalized_gold, gold_info = canonicalize_workflow_graph(gold)
        normalized_candidate, candidate_info = canonicalize_workflow_graph(candidate)
        self.assertEqual(normalized_gold, normalized_candidate)
        self.assertEqual(gold_info.topological_orders_considered, 2)
        self.assertEqual(candidate_info.topological_orders_considered, 2)

    def test_real_branch_node_edge_artifact_and_owner_changes_differ(self) -> None:
        gold = _branch_workflow()
        mutations = []
        node = copy.deepcopy(gold)
        node["action"]["steps"][1]["verification"] = "auto"
        mutations.append(node)
        artifact = copy.deepcopy(gold)
        artifact["action"]["steps"][1]["arguments"]["result_path"] = "${segment.artifacts.class_probabilities}"
        mutations.append(artifact)
        edge = copy.deepcopy(gold)
        edge["action"]["steps"][1]["arguments"]["result_path"] = "/tmp/wrong.bin"
        edge["action"]["steps"][1]["depends_on"] = []
        mutations.append(edge)
        for candidate in mutations:
            self.assertLess(self.reward.score(candidate, gold).total, 1.0)

    def test_structured_argument_verification_and_stop_references_rename(self) -> None:
        payload = {
            "argument_ref": "${old.artifacts.point_labels}",
            "verification_target_step_id": "old",
            "verification": {"verification_owner": "old", "verification_target": "old"},
            "stop": {"stop_step_id": "old", "stop_target_step_id": "old"},
            "free_text": "old",
        }
        rewritten = rewrite_step_references(payload, {"old": "step_0"})
        self.assertEqual(rewritten["argument_ref"], "${step_0.artifacts.point_labels}")
        self.assertEqual(rewritten["verification_target_step_id"], "step_0")
        self.assertEqual(rewritten["verification"]["verification_owner"], "step_0")
        self.assertEqual(rewritten["stop"]["stop_step_id"], "step_0")
        self.assertEqual(rewritten["free_text"], "old")

    def test_inconsistent_rename_undefined_ref_and_cycle_are_invalid(self) -> None:
        gold = _branch_workflow()
        inconsistent = copy.deepcopy(gold)
        inconsistent["action"]["steps"][0]["step_id"] = "renamed_only"
        undefined = copy.deepcopy(gold)
        undefined["action"]["steps"][1]["arguments"]["result_path"] = "${missing.artifacts.point_labels}"
        cycle = copy.deepcopy(gold)
        cycle["action"]["steps"][0]["depends_on"] = ["check_labels"]
        for candidate in (inconsistent, undefined, cycle):
            score = self.reward.score(candidate, gold)
            self.assertTrue(score.invalid)
            self.assertEqual(score.total, 0.0)

    def test_invalid_schema_hard_zero(self) -> None:
        for gold in self.golds:
            invalid = next(item for item in generate_mutations(gold) if item.family == "invalid_schema")
            score = self.reward.score(invalid.candidate, gold)
            self.assertTrue(score.invalid)
            self.assertEqual(score.total, 0.0)


if __name__ == "__main__":
    unittest.main()
