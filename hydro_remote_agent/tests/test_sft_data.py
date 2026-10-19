from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.data.sft import (
    SFTDataError,
    build_system_prompt,
    compact_tool_catalog,
    format_sft_dataset,
    format_sft_record,
)
from hydro_remote_agent.data.vague_hydro import load_jsonl
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"
ONTOLOGY_PATH = PACKAGE_ROOT / "data" / "schema" / "ontology.json"
MANIFEST_PATH = PACKAGE_ROOT / "data" / "vague_hydro" / "source_manifest.jsonl"
CANONICAL_DIR = PACKAGE_ROOT / "data" / "vague_hydro"


class SFTDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_tool_registry(REGISTRY_PATH)
        cls.ontology = json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))
        cls.manifest = {
            record["sample_id"]: record for record in load_jsonl(MANIFEST_PATH)
        }

    def test_formatter_injects_assets_tools_and_strict_target(self) -> None:
        record = load_jsonl(CANONICAL_DIR / "canonical_train.jsonl")[0]
        formatted = format_sft_record(
            record,
            self.manifest[record["sample_id"]],
            build_system_prompt(self.ontology),
            compact_tool_catalog(self.registry),
            self.registry,
        )
        self.assertEqual([message["role"] for message in formatted["messages"]], [
            "system",
            "user",
            "assistant",
        ])
        user = json.loads(formatted["messages"][1]["content"])
        target = json.loads(formatted["messages"][2]["content"])
        self.assertIn("image_path", user["assets"])
        self.assertIn("point_cloud_path", user["assets"])
        self.assertEqual(user["request_id"], formatted["id"])
        self.assertNotIn("point_labels_path", user["assets"])
        self.assertEqual(target, record["gold_request"])
        self.assertEqual(formatted["images"], [user["assets"]["image_path"]])
        self.assertEqual(
            formatted["media"]["point_clouds"],
            [user["assets"]["point_cloud_path"]],
        )
        self.assertEqual(len(formatted["tools"]), 6)
        self.assertEqual(
            [tool["function"]["name"] for tool in formatted["tools"]],
            sorted(self.registry.names()),
        )

    def test_formatter_rejects_manifest_split_mismatch(self) -> None:
        record = load_jsonl(CANONICAL_DIR / "canonical_train.jsonl")[0]
        manifest = dict(self.manifest[record["sample_id"]])
        manifest["split"] = "test"
        with self.assertRaisesRegex(SFTDataError, "split mismatch"):
            format_sft_record(
                record,
                manifest,
                build_system_prompt(self.ontology),
                compact_tool_catalog(self.registry),
                self.registry,
            )

    def test_dataset_formatter_writes_three_splits_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            for split in ("train", "val", "test"):
                source = load_jsonl(CANONICAL_DIR / f"canonical_{split}.jsonl")[0]
                (input_dir / f"vague_hydro_{split}.jsonl").write_text(
                    json.dumps(source, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            report = format_sft_dataset(
                input_dir,
                output_dir,
                MANIFEST_PATH,
                self.ontology,
                self.registry,
            )
            self.assertEqual(report["record_count"], 3)
            self.assertEqual(report["sample_split_overlap_count"], 0)
            self.assertEqual(report["status"], "passed")
            self.assertTrue((output_dir / "train_sft.jsonl").exists())
            self.assertTrue((output_dir / "sft_report.json").exists())

    def test_formatter_rewrites_assets_and_gold_action_paths(self) -> None:
        record = load_jsonl(CANONICAL_DIR / "canonical_train.jsonl")[1]
        source = "/data/wcs10m"
        target = "/new/data/10M"
        formatted = format_sft_record(
            record,
            self.manifest[record["sample_id"]],
            build_system_prompt(self.ontology),
            compact_tool_catalog(self.registry),
            self.registry,
            [(source, target)],
        )
        user = json.loads(formatted["messages"][1]["content"])
        assistant = json.loads(formatted["messages"][2]["content"])
        self.assertTrue(user["assets"]["image_path"].startswith(target))
        serialized_target = json.dumps(assistant)
        self.assertNotIn(source, serialized_target)
        self.assertIn(target, serialized_target)


if __name__ == "__main__":
    unittest.main()
