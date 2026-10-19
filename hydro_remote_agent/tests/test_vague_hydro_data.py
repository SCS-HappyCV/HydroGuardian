from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.data.vague_hydro import (
    VagueHydroAuditError,
    audit_asset_paths,
    audit_dataset,
    build_canonical_records,
    build_source_manifest,
)
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"


def _source_record() -> dict:
    return {
        "sample_id": "00_000000",
        "patch_id": "000000",
        "region_id": "00",
        "ortho_image_path": "/dataset/00/image/000000.png",
        "point_cloud_path": "/dataset/00/velodyne/000000.txt",
        "point_labels_path": "/dataset/00/velodyne/000000.txt",
        "texts": [
            {
                "text_id": "00_000000_class_9_1",
                "task_type": "class",
                "text": "Is grassland present?",
                "target_label_ids": [9],
                "target_label_names": ["Grassland"],
            },
            {
                "text_id": "00_000000_attribute_9_2",
                "task_type": "attribute",
                "text": "Is there a vegetated area?",
                "target_label_ids": [9],
                "target_label_names": ["Grassland"],
                "attributes": ["vegetated"],
                "attribute_phrases": ["low vegetation"],
            },
            {
                "text_id": "00_000000_relation_4_near_12_3",
                "task_type": "relation",
                "text": "Is the dirt road near bare land?",
                "target_label_ids": [4],
                "target_label_names": ["Dirtroad"],
                "reference_label_ids": [12],
                "reference_label_names": ["Bareland"],
                "target_mask_rule": {
                    "type": "near",
                    "source_label": 4,
                    "reference_label": 12,
                    "distance_threshold_m": 3.0,
                },
            },
            {
                "text_id": "00_000000_no_target_1_4",
                "task_type": "no_target",
                "text": "Is a shed present?",
                "target_label_ids": [1],
                "target_label_names": ["Shed"],
                "is_no_target": True,
                "no_target_type": "class_absent",
            },
        ],
    }


class VagueHydroDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)
        self.sources = [_source_record()]
        self.manifest = build_source_manifest(self.sources, {"00_000000": "train"})

    def test_builder_preserves_direct_semantics_and_derives_dense_actions(self) -> None:
        records = build_canonical_records(self.sources, self.manifest)
        self.assertEqual(len(records), 9)
        by_id = {record["query_id"]: record for record in records}

        class_direct = by_id["q:00-000000-class-9-1:direct"]
        self.assertEqual(class_direct["gold_request"]["action"]["type"], "direct_answer")
        self.assertEqual(class_direct["canonical_intent"], "class_presence")
        self.assertEqual(class_direct["query"], "Is Grassland present in this scene?")
        self.assertEqual(
            class_direct["provenance"]["source_query"],
            "Is grassland present?",
        )

        class_dense = by_id["q:00-000000-class-9-1:dense"]
        self.assertEqual(class_dense["gold_request"]["action"]["tool"], "multimodal_semantic_segmentation")
        self.assertEqual(class_dense["output_granularity"], "point_mask")

        attribute_dense = by_id["q:00-000000-attribute-9-2:dense"]
        self.assertEqual(attribute_dense["gold_request"]["action"]["tool"], "language_guided_point_segmentation")
        self.assertIn("vegetated", attribute_dense["query"])
        self.assertIn("low vegetation", attribute_dense["query"])
        self.assertEqual(
            attribute_dense["gold_request"]["action"]["arguments"]["query"],
            attribute_dense["query"],
        )
        attribute_direct = by_id["q:00-000000-attribute-9-2:direct"]
        self.assertIn("vegetated", attribute_direct["query"])
        self.assertIn("low vegetation", attribute_direct["query"])

        no_target_direct = by_id["q:00-000000-no-target-1-4:direct"]
        self.assertTrue(no_target_direct["supervision"]["is_no_target"])
        self.assertTrue(no_target_direct["gold_request"]["action"]["answer"].startswith("No."))

    def test_relation_dense_action_is_executable_workflow(self) -> None:
        records = build_canonical_records(self.sources, self.manifest)
        relation = next(
            record
            for record in records
            if record["query_id"] == "q:00-000000-relation-4-near-12-3:dense"
        )
        action = relation["gold_request"]["action"]
        self.assertEqual(action["type"], "workflow")
        self.assertEqual([step["tool"] for step in action["steps"]], [
            "multimodal_semantic_segmentation",
            "geometry_relation_analysis",
        ])
        self.assertEqual(
            action["steps"][1]["arguments"]["segmentation_result_path"],
            "${segment_scene.artifacts.point_labels}",
        )
        report = audit_dataset(self.manifest, records, self.registry)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["failure_count"], 0)

    def test_manifest_records_annotation_evidence_without_claiming_full_label_scan(self) -> None:
        summary = self.manifest[0]["annotation_summary"]
        self.assertEqual(summary["annotation_supported_label_ids"], [4, 9, 12])
        self.assertEqual(summary["annotation_absent_label_ids"], [1])
        self.assertEqual(summary["task_type_counts"]["relation"], 1)

    def test_split_mismatch_is_rejected(self) -> None:
        records = build_canonical_records(self.sources, self.manifest)
        corrupted = copy.deepcopy(records)
        corrupted[0]["split"] = "test"
        with self.assertRaisesRegex(VagueHydroAuditError, "disagrees with manifest"):
            audit_dataset(self.manifest, corrupted, self.registry)

    def test_invalid_relation_rule_is_rejected(self) -> None:
        sources = copy.deepcopy(self.sources)
        sources[0]["texts"][2]["target_mask_rule"]["type"] = "behind"
        with self.assertRaisesRegex(VagueHydroAuditError, "unsupported relation"):
            build_source_manifest(sources, {"00_000000": "train"})

    def test_asset_audit_checks_remapped_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for relative_path in (
                "00/image/000000.png",
                "00/velodyne/000000.txt",
            ):
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"test")
            report = audit_asset_paths(
                self.manifest,
                path_mappings=[("/dataset", root.as_posix())],
                require_all=True,
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["missing_counts"], {})

    def test_audit_reports_cross_split_exact_query_collisions(self) -> None:
        second = copy.deepcopy(self.sources[0])
        second["sample_id"] = "01_000001"
        second["patch_id"] = "000001"
        second["region_id"] = "01"
        second["ortho_image_path"] = "/dataset/01/image/000001.png"
        second["point_cloud_path"] = "/dataset/01/velodyne/000001.txt"
        second["point_labels_path"] = second["point_cloud_path"]
        for text_item in second["texts"]:
            text_item["text_id"] = str(text_item["text_id"]).replace("00_000000", "01_000001")
        sources = [self.sources[0], second]
        manifest = build_source_manifest(
            sources,
            {"00_000000": "train", "01_000001": "test"},
        )
        records = build_canonical_records(
            sources,
            manifest,
            include_dense_variants=False,
            include_full_scene_tasks=False,
        )
        report = audit_dataset(manifest, records, self.registry)
        self.assertGreater(report["cross_split_exact_query_collision_count"], 0)


if __name__ == "__main__":
    unittest.main()
