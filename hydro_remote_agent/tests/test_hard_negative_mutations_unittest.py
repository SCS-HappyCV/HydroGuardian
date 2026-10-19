from __future__ import annotations

import json
import unittest
from pathlib import Path

from hydro_remote_agent.rewards.hard_negative_mutations import generate_mutations
from hydro_remote_agent.rewards.request_canonicalizer import canonicalize_agent_request
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml")
MANIFEST = ROOT / "runs/hydro_remote_agent/vaguehydro_grpo_reward_design_v1/DATA_MANIFEST.json"


class HardNegativeMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.golds = {
            action_type: next(item["gold_action"] for item in manifest["records"] if item["action_type"] == action_type)
            for action_type in ("tool_call", "workflow")
        }

    def test_expected_families_and_validity(self) -> None:
        expected = {
            "tool_call": {"tool_replacement", "argument_value", "argument_slot", "verification_stop", "invalid_schema"},
            "workflow": {"tool_replacement", "argument_value", "argument_slot", "workflow_node", "dag_link", "artifact_reference", "verification_stop", "invalid_schema"},
        }
        for action_type, gold in self.golds.items():
            mutations = generate_mutations(gold)
            self.assertTrue(expected[action_type] <= {item.family for item in mutations})
            for item in mutations:
                self.assertIs(type(item.equivalence), bool, item.name)
                self.assertEqual(canonicalize_agent_request(item.candidate, REGISTRY).valid, item.valid_expected, item.name)
            if action_type == "workflow":
                self.assertFalse(next(item for item in mutations if item.family == "dag_link").equivalence)

    def test_equivalence_controls_valid(self) -> None:
        for gold in self.golds.values():
            for item in generate_mutations(gold):
                if item.equivalence:
                    self.assertTrue(canonicalize_agent_request(item.candidate, REGISTRY).valid, item.name)

    def test_deterministic(self) -> None:
        for gold in self.golds.values():
            first = [item.to_dict() for item in generate_mutations(gold)]
            second = [item.to_dict() for item in generate_mutations(gold)]
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
