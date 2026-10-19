from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.evaluation.manifest import (
    build_eval_manifest,
    select_stratified_unique,
)


def make_record(index: int, language: str, level: str, action: str) -> dict:
    record_id = f"q:{language}:{level}:{action}:{index}"
    target = {
        "schema_version": "1.0",
        "request_id": record_id,
        "intent": "class_presence",
        "action": {"type": action},
    }
    return {
        "id": record_id,
        "sample_id": f"sample:{language}:{level}:{action}:{index}",
        "language": language,
        "ambiguity_level": level,
        "images": [f"/data/{record_id}.png"],
        "messages": [{"role": "assistant", "content": json.dumps(target)}],
    }


class AgentEvalManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [
            make_record(index, language, level, action)
            for language in ("en", "zh")
            for level in ("L0", "L1")
            for action in ("direct_answer", "tool_call", "workflow")
            for index in range(3)
        ]

    def test_selection_is_balanced_unique_and_deterministic(self) -> None:
        first = select_stratified_unique(self.records, count=24, seed=7)
        second = select_stratified_unique(self.records, count=24, seed=7)
        self.assertEqual([row["id"] for row in first], [row["id"] for row in second])
        self.assertEqual(len({row["sample_id"] for row in first}), 24)

    def test_count_must_divide_bucket_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "divisible"):
            select_stratified_unique(self.records, count=13, seed=7)

    def test_manifest_audits_training_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "test.jsonl"
            training_path = root / "train.jsonl"
            manifest_path = root / "gold.jsonl"
            report_path = root / "report.json"
            input_path.write_text(
                "".join(json.dumps(row) + "\n" for row in self.records),
                encoding="utf-8",
            )
            training_path.write_text(
                json.dumps(make_record(99, "en", "L0", "direct_answer")) + "\n",
                encoding="utf-8",
            )
            report = build_eval_manifest(
                input_path,
                training_path,
                manifest_path,
                report_path,
                count=24,
                seed=7,
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["unique_sample_id_count"], 24)
            self.assertTrue(manifest_path.exists())


if __name__ == "__main__":
    unittest.main()
