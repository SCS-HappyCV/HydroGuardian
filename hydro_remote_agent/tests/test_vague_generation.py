from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.data.vague_generation import (
    GenerationCache,
    VagueGenerationError,
    build_generation_prompt,
    deduplicate_exact_queries,
    generation_input_fingerprint,
    materialize_variants,
    semantic_signature,
    validate_generation_payload,
)
from hydro_remote_agent.tools.generate_vague_queries import _thinking_options


def _canonical_record(split: str = "train") -> dict:
    query_id = "q:00-000000-class-9-1:dense"
    return {
        "schema_version": "vague_hydro.canonical.v1",
        "query_id": query_id,
        "sample_id": "00_000000",
        "split": split,
        "language": "en",
        "ambiguity_level": "L0",
        "query": "Segment every Grassland point in this scene.",
        "canonical_intent": "class_segmentation",
        "output_granularity": "point_mask",
        "gold_request": {
            "schema_version": "1.0",
            "request_id": query_id,
            "intent": "class_segmentation",
            "action": {
                "type": "tool_call",
                "tool": "multimodal_semantic_segmentation",
                "arguments": {
                    "image_path": "/private/image.png",
                    "point_cloud_path": "/private/points.txt",
                },
            },
            "expected_output": {
                "type": "point_mask",
                "coordinate_space": "source_point_cloud",
            },
        },
        "supervision": {
            "source_task_type": "class",
            "target_label_ids": [9],
            "target_label_names": ["Grassland"],
            "is_no_target": False,
        },
        "provenance": {"source_text_id": "00_000000_class_9_1"},
    }


def _payload(record: dict, language: str = "en") -> dict:
    if language == "en":
        queries = [
            "Mark every Grassland point.",
            "Locate all points representing Grassland.",
            "Show the point-level extent of the Grassland area.",
            "Map the relevant Grassland points for the field review.",
        ]
    else:
        queries = [
            "标出全部草地点。",
            "定位场景中所有草地对应的点。",
            "给出草地区域的逐点范围。",
            "为现场复核绘制草地区域的点级范围。",
        ]
    return {
        "items": [
            {
                "parent_query_id": record["query_id"],
                "semantic_check": semantic_signature(record),
                "variants": [
                    {"level": level, "query": query}
                    for level, query in zip(("L0", "L1", "L2", "L3"), queries)
                ],
            }
        ]
    }


class VagueGenerationTest(unittest.TestCase):
    def test_batch_chat_disables_thinking_at_body_top_level(self) -> None:
        batch_options = _thinking_options(
            "https://batch.dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.assertEqual(batch_options, {"enable_thinking": False})
        realtime_options = _thinking_options(
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.assertIn("chat_template_kwargs", realtime_options)

    def test_prompt_excludes_paths_and_internal_tool_names(self) -> None:
        record = _canonical_record()
        _, prompt = build_generation_prompt([record], "en")
        self.assertNotIn("/private/image.png", prompt)
        self.assertNotIn("multimodal_semantic_segmentation", prompt.split("Input tasks:", 1)[1])
        self.assertIn("class_segmentation", prompt)

    def test_prompt_requires_explicit_point_cue_at_every_level(self) -> None:
        record = _canonical_record()
        _, prompt = build_generation_prompt([record], "en")
        self.assertIn(
            '"required_output_cues": [\n      "point",\n      "points",\n      "point-level"',
            prompt,
        )
        self.assertIn("each L0/L1/L2/L3 query MUST literally contain", prompt)
        self.assertIn("area, extent, map, region, or", prompt)

    def test_payload_validation_and_materialization(self) -> None:
        record = _canonical_record()
        validated = validate_generation_payload(_payload(record), [record], "en")
        variants = materialize_variants(
            record,
            validated[record["query_id"]],
            "en",
            "fake-model",
            "response-1",
        )
        self.assertEqual(len(variants), 4)
        self.assertEqual(variants[3]["ambiguity_level"], "L3")
        self.assertEqual(
            variants[0]["gold_request"]["request_id"],
            variants[0]["query_id"],
        )

    def test_semantic_drift_is_rejected(self) -> None:
        record = _canonical_record()
        payload = _payload(record)
        payload["items"][0]["semantic_check"]["target_label_ids"] = [13]
        with self.assertRaisesRegex(VagueGenerationError, "semantic signature drift"):
            validate_generation_payload(payload, [record], "en")

    def test_semantic_signature_preserves_dense_attribute_phrases(self) -> None:
        record = _canonical_record()
        record["canonical_intent"] = "attribute_segmentation"
        record["supervision"]["attributes"] = ["vegetated"]
        record["supervision"]["attribute_phrases"] = ["contiguous", "broad extent"]
        self.assertEqual(
            semantic_signature(record)["attributes"],
            ["vegetated", "contiguous", "broad extent"],
        )

    def test_point_mask_rejects_pixel_or_missing_point_output(self) -> None:
        record = _canonical_record()
        payload = _payload(record)
        payload["items"][0]["variants"][1]["query"] = "Mask every Grassland pixel."
        with self.assertRaisesRegex(VagueGenerationError, "point output"):
            validate_generation_payload(payload, [record], "en")

        payload = _payload(record)
        payload["items"][0]["variants"][2]["query"] = "Map the Grassland area."
        with self.assertRaisesRegex(VagueGenerationError, "point-level output"):
            validate_generation_payload(payload, [record], "en")

    def test_presence_judgement_rejects_localization_request(self) -> None:
        record = _canonical_record()
        record["query_id"] = "q:00-000000-class-9-1:direct"
        record["canonical_intent"] = "class_presence"
        record["output_granularity"] = "text_answer"
        record["gold_request"]["request_id"] = record["query_id"]
        payload = {
            "items": [
                {
                    "parent_query_id": record["query_id"],
                    "semantic_check": semantic_signature(record),
                    "variants": [
                        {"level": "L0", "query": "Does this scene contain Grassland?"},
                        {"level": "L1", "query": "Can you confirm whether Grassland is present?"},
                        {"level": "L2", "query": "Check whether the current view includes Grassland."},
                        {"level": "L3", "query": "Where is the Grassland in this scene?"},
                    ],
                }
            ]
        }
        with self.assertRaisesRegex(VagueGenerationError, "changes a judgement"):
            validate_generation_payload(payload, [record], "en")

    def test_controlled_class_term_rejects_narrower_target(self) -> None:
        record = _canonical_record()
        payload = _payload(record)
        payload["items"][0]["variants"][2]["query"] = (
            "Show the point-level extent of low meadow vegetation."
        )
        with self.assertRaisesRegex(VagueGenerationError, "controlled target class"):
            validate_generation_payload(payload, [record], "en")

    def test_identical_query_is_preserved_across_different_scenes(self) -> None:
        train = _canonical_record("train")
        test = copy.deepcopy(train)
        test["split"] = "test"
        test["sample_id"] = "01_000001"
        test["query_id"] = "q:01-000001-class-9-1:dense"
        test["gold_request"]["request_id"] = test["query_id"]
        kept, report = deduplicate_exact_queries([train, test])
        self.assertEqual(len(kept), 2)
        self.assertEqual(report["dropped_exact_duplicate_count"], 0)
        self.assertEqual(report["cross_scene_exact_query_count"], 1)

    def test_identical_query_with_conflicting_semantics_fails_within_scene(self) -> None:
        present = _canonical_record("train")
        absent = copy.deepcopy(present)
        absent["query_id"] = "q:00-000000-no-target-9-2:direct"
        absent["gold_request"]["request_id"] = absent["query_id"]
        absent["supervision"]["is_no_target"] = True
        with self.assertRaisesRegex(VagueGenerationError, "identical queries"):
            deduplicate_exact_queries([present, absent])

    def test_generation_cache_round_trip(self) -> None:
        record = _canonical_record()
        item = _payload(record)["items"][0]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = GenerationCache(Path(temp_dir) / "cache.sqlite")
            try:
                cache.set(record["query_id"], "en", "fake-model", item, "response-1")
                loaded = cache.get(record["query_id"], "en", "fake-model")
                self.assertIsNotNone(loaded)
                assert loaded is not None
                self.assertEqual(loaded["item"], item)
                self.assertEqual(cache.count(), 1)
            finally:
                cache.close()

    def test_generation_cache_invalidates_changed_canonical_input(self) -> None:
        record = _canonical_record()
        item = _payload(record)["items"][0]
        fingerprint = generation_input_fingerprint(record)
        changed = copy.deepcopy(record)
        changed["query"] = "Segment only contiguous Grassland points."
        changed_fingerprint = generation_input_fingerprint(changed)
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = GenerationCache(Path(temp_dir) / "cache.sqlite")
            try:
                cache.set(
                    record["query_id"],
                    "en",
                    "fake-model",
                    item,
                    "response-1",
                    fingerprint,
                )
                self.assertIsNotNone(
                    cache.get(record["query_id"], "en", "fake-model", fingerprint)
                )
                self.assertIsNone(
                    cache.get(record["query_id"], "en", "fake-model", changed_fingerprint)
                )
            finally:
                cache.close()


if __name__ == "__main__":
    unittest.main()
