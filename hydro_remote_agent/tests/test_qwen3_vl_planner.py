from __future__ import annotations

import json
import unittest

from hydro_remote_agent.tools.predict_qwen3_vl_routing import (
    _rewrite_image_paths,
    build_parser,
)

from hydro_remote_agent.backbones.qwen3_vl_planner import (
    iter_batches,
    planner_messages,
    planner_system_prompt,
    stratified_sample,
)


def make_record(record_id: str, language: str, level: str, action_type: str):
    target = {
        "schema_version": "1.0",
        "request_id": record_id,
        "intent": "test",
        "action": {"type": action_type},
    }
    return {
        "id": record_id,
        "language": language,
        "ambiguity_level": level,
        "images": ["tile.png"],
        "tools": [{"type": "function", "function": {"name": "demo"}}],
        "messages": [
            {"role": "system", "content": "Plan."},
            {"role": "user", "content": json.dumps({"query": "test", "assets": {}})},
            {"role": "assistant", "content": json.dumps(target)},
        ],
    }


class Qwen3VLPlannerTest(unittest.TestCase):
    def test_rewrite_image_paths_only_changes_physical_image_block(self):
        conversations = [[{
            "role": "user",
            "content": [
                {"type": "image", "image": "/data/10M/01/image/a.png"},
                {"type": "text", "text": "asset=/data/10M/01/image/a.png"},
            ],
        }]]

        _rewrite_image_paths(conversations, "/data/10M", "/tmp/cache")

        self.assertEqual(
            conversations[0][0]["content"][0]["image"],
            "/tmp/cache/01/image/a.png",
        )
        self.assertEqual(
            conversations[0][0]["content"][1]["text"],
            "asset=/data/10M/01/image/a.png",
        )

    def test_stratified_sample_covers_each_bucket(self) -> None:
        records = []
        for language in ("en", "zh"):
            for level in ("L0", "L1"):
                for action in ("direct_answer", "tool_call", "workflow"):
                    records.append(make_record(f"{language}-{level}-{action}", language, level, action))
        sampled = stratified_sample(records, len(records), seed=7)
        self.assertEqual({record["id"] for record in sampled}, {record["id"] for record in records})
        self.assertEqual(
            stratified_sample(records, 5, seed=7),
            stratified_sample(records, 5, seed=7),
        )

    def test_planner_messages_inject_request_id_and_omit_gold(self) -> None:
        record = make_record("query-1", "en", "L0", "tool_call")
        messages = planner_messages(record)
        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        user = json.loads(messages[1]["content"][1]["text"])
        self.assertEqual(user["request_id"], "query-1")
        serialized = json.dumps(messages)
        self.assertNotIn('"intent": "test"', serialized)
        self.assertIn("Available tools", messages[0]["content"][0]["text"])

    def test_iter_batches_rejects_invalid_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            list(iter_batches([1], 0))
        self.assertEqual(list(iter_batches([1, 2, 3], 2)), [[1, 2], [3]])

    def test_prompt_ablation_profiles_remove_only_requested_content(self) -> None:
        record = make_record("query-1", "en", "L0", "tool_call")
        record["tools"][0]["function"].update(
            {
                "description": "demo capability",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "asset path"}},
                },
            }
        )
        full = planner_system_prompt(record)
        no_descriptions = planner_system_prompt(record, "no_tool_descriptions")
        no_examples = planner_system_prompt(record, "no_request_examples")
        no_workflow = planner_system_prompt(record, "no_workflow_example")
        minimal = planner_system_prompt(record, "minimal_toolspec")
        self.assertIn("demo capability", full)
        self.assertNotIn("demo capability", no_descriptions)
        self.assertIn('"path":{"type":"string"}', no_descriptions)
        self.assertNotIn("Valid complete AgentRequest examples", no_examples)
        self.assertNotIn('"request_id":"example:workflow"', no_workflow)
        self.assertIn('"request_id":"example:tool"', no_workflow)
        self.assertNotIn("demo capability", minimal)
        self.assertNotIn("Valid complete AgentRequest examples", minimal)
        self.assertIn('"path":{"type":"string"}', minimal)

    def test_predict_parser_accepts_frozen_manifest_options(self) -> None:
        args = build_parser().parse_args(
            [
                "--config", "backbone.json",
                "--input", "gold.jsonl",
                "--output", "predictions.jsonl",
                "--sample-manifest", "selected.jsonl",
                "--no-resample",
                "--merge-adapter",
                "--max-image-pixels", "262144",
                "--model-path", "/tmp/model",
            ]
        )
        self.assertTrue(args.no_resample)
        self.assertTrue(args.merge_adapter)
        self.assertEqual(args.max_image_pixels, 262144)
        self.assertEqual(args.model_path, "/tmp/model")
        self.assertEqual(args.prompt_profile, "full")


if __name__ == "__main__":
    unittest.main()
