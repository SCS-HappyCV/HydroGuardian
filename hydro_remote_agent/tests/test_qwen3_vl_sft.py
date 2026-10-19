from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.training.qwen3_vl_sft import (
    JsonlOffsetDataset,
    find_last_subsequence,
    training_messages,
    training_target,
)


class Qwen3VLSFTTest(unittest.TestCase):
    def test_jsonl_offset_dataset_is_lazy_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data.jsonl"
            path.write_text(
                "\n".join(json.dumps({"id": index}) for index in range(3)) + "\n",
                encoding="utf-8",
            )
            dataset = JsonlOffsetDataset(path, max_samples=2)
            self.assertEqual(len(dataset), 2)
            self.assertEqual(dataset[1]["id"], 1)

    def test_find_last_subsequence(self) -> None:
        self.assertEqual(find_last_subsequence([1, 2, 3, 2, 3], [2, 3]), 3)
        self.assertEqual(find_last_subsequence([1, 2], [3]), -1)
        self.assertEqual(find_last_subsequence([1, 2], []), -1)

    def test_unknown_target_format_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported SFT target format"):
            training_messages({}, "unknown")
        with self.assertRaisesRegex(ValueError, "unsupported SFT target format"):
            training_target({}, "unknown")


if __name__ == "__main__":
    unittest.main()
