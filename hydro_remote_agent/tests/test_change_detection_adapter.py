from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from hydro_remote_agent.runtime.change_detection_adapter import (
    ChangeDetectionAdapter,
    extract_change_regions,
)
from hydro_remote_agent.runtime.change_detection_engine import ChangeDetectionPrediction
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"


class FakeChangeDetectionEngine:
    def __init__(self, probability_map: np.ndarray) -> None:
        self.initialized = False
        self.probability_map = probability_map
        self.calls = []

    def prepare(self) -> None:
        self.initialized = True

    def predict(self, before_image_path: str, after_image_path: str):
        self.calls.append((before_image_path, after_image_path))
        return ChangeDetectionPrediction(
            probability_map=self.probability_map,
            original_size=self.probability_map.shape,
            device="cuda:0",
        )


class ChangeDetectionAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)

    def test_region_filter_removes_small_components(self) -> None:
        probability = np.zeros((6, 7), dtype=np.float32)
        probability[1:3, 1:4] = 0.8
        probability[5, 6] = 0.9
        mask, regions = extract_change_regions(probability, 0.5, 3)
        self.assertEqual(int(mask.sum()), 6)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["bbox_xywh"], [1, 1, 3, 2])
        self.assertAlmostEqual(regions[0]["mean_probability"], 0.8, places=6)

    def test_adapter_writes_mask_probability_regions_and_manifest(self) -> None:
        probability = np.zeros((5, 8), dtype=np.float32)
        probability[1:4, 2:6] = 0.75
        engine = FakeChangeDetectionEngine(probability)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            adapter = ChangeDetectionAdapter(
                tool_spec=self.registry.get("image_change_detection"),
                work_dir=root,
                checkpoint_path="best_model.pth",
                vendor_root="vendor/change_detection",
                engine=engine,
            )
            self.assertEqual(adapter.prepare().status, "ready")
            result = adapter.predict(
                "change_01",
                {
                    "before_image_path": "before.png",
                    "after_image_path": "after.png",
                    "change_threshold": 0.6,
                    "minimum_region_pixels": 5,
                },
            )
            self.assertFalse(result.is_mock)
            self.assertEqual(result.backend, "rfanet_change_detection")
            mask = np.asarray(Image.open(result.artifacts["change_mask"]).convert("L"))
            self.assertEqual(mask.shape, probability.shape)
            self.assertEqual(int(np.count_nonzero(mask)), 12)
            with np.load(result.artifacts["change_probability_map"], allow_pickle=False) as payload:
                np.testing.assert_array_equal(payload["change_probability_map"], probability)
            regions = json.loads(
                Path(result.artifacts["change_regions"]).read_text(encoding="utf-8")
            )
            self.assertEqual(regions["changed_pixels"], 12)
            self.assertEqual(len(regions["regions"]), 1)
            self.assertTrue(Path(result.manifest_path).is_file())


if __name__ == "__main__":
    unittest.main()
