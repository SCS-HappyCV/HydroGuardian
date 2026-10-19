from __future__ import annotations

import json
import unittest

from hydro_remote_agent.training.curriculum import select_curriculum


def record(index: int, action: str, language: str, level: str, tile: str) -> dict:
    request = {"action": {"type": action}}
    return {
        "id": f"q:{index}",
        "sample_id": tile,
        "language": language,
        "ambiguity_level": level,
        "metadata": {"parent_query_id": f"parent:{index // 2}"},
        "messages": [{"role": "assistant", "content": json.dumps(request)}],
    }


class Qwen3VLCurriculumTest(unittest.TestCase):
    def test_selection_satisfies_action_and_language_level_balance(self) -> None:
        records = []
        index = 0
        for action in ("direct_answer", "tool_call", "workflow"):
            for language in ("en", "zh"):
                for level in ("L0", "L1"):
                    for repeat in range(4):
                        records.append(record(index, action, language, level, f"tile:{repeat}"))
                        index += 1
        selected = select_curriculum(
            records,
            action_quotas={"direct_answer": 4, "tool_call": 4, "workflow": 4},
            seed=3,
            max_records_per_tile=4,
            max_parent_variants={"direct_answer": 2, "tool_call": 2, "workflow": 2},
        )
        self.assertEqual(len(selected), 12)
        for action in ("direct_answer", "tool_call", "workflow"):
            subset = [item for item in selected if json.loads(item["messages"][0]["content"])["action"]["type"] == action]
            self.assertEqual(len(subset), 4)
            self.assertEqual({(item["language"], item["ambiguity_level"]) for item in subset}, {("en", "L0"), ("en", "L1"), ("zh", "L0"), ("zh", "L1")})


if __name__ == "__main__":
    unittest.main()
