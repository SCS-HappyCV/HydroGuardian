from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path

import numpy as np

from hydro_remote_agent.runtime.gufnet_adapter import (
    MultimodalGufnetAdapter,
    PointGufnetAdapter,
)
from hydro_remote_agent.runtime.gufnet_engine import GufnetInferenceEngine, GufnetPrediction
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"


class FakeGufnetEngine:
    def __init__(self) -> None:
        self.initialized = False
        self.calls = []
        self.max_chunk_points = 100000
        self.min_chunk_points = 12500

    def prepare(self) -> None:
        self.initialized = True

    def predict(self, point_cloud_path: str) -> GufnetPrediction:
        self.calls.append(point_cloud_path)
        probabilities = np.zeros((4, 15), dtype=np.float32)
        labels = np.asarray([1, 4, 4, 13], dtype=np.int32)
        probabilities[np.arange(4), labels - 1] = 1.0
        return GufnetPrediction(labels, probabilities, 4, "cuda:0")


class GufnetAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)

    def _adapter(self, cls, tool_name: str, work_dir: Path, engine: FakeGufnetEngine):
        return cls(
            tool_spec=self.registry.get(tool_name),
            work_dir=work_dir,
            checkpoint_path="checkpoint.ckpt",
            config_path="config.yaml",
            vendor_root="vendor/gufnet",
            engine=engine,
        )

    def test_point_adapter_writes_real_segmentation_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine = FakeGufnetEngine()
            adapter = self._adapter(
                PointGufnetAdapter, "point_semantic_segmentation", root, engine
            )
            self.assertEqual(adapter.prepare().status, "ready")
            result = adapter.predict(
                "point_01",
                {"point_cloud_path": "tile.txt", "target_class_ids": [4, 13]},
            )
            self.assertFalse(result.is_mock)
            self.assertEqual(result.backend, "gufnet_3d_inference")
            self.assertEqual(result.metrics["num_points"], 4)
            with np.load(result.artifacts["point_labels"], allow_pickle=False) as payload:
                np.testing.assert_array_equal(payload["point_labels"], [1, 4, 4, 13])
            with np.load(result.artifacts["class_probabilities"], allow_pickle=False) as payload:
                self.assertEqual(payload["class_probabilities"].shape, (4, 15))
                np.testing.assert_array_equal(payload["class_ids"], np.arange(1, 16))
            with np.load(result.artifacts["class_masks"], allow_pickle=False) as payload:
                np.testing.assert_array_equal(payload["class_ids"], [4, 13])
                np.testing.assert_array_equal(
                    payload["class_masks"],
                    [[False, True, True, False], [False, False, False, True]],
                )
            summary = json.loads(
                Path(result.artifacts["class_summary"]).read_text(encoding="utf-8")
            )
            self.assertEqual(summary["num_points"], 4)
            self.assertEqual(summary["num_present_classes"], 3)
            self.assertEqual(summary["classes"][0]["class_name"], "土路")
            self.assertEqual(summary["classes"][0]["point_count"], 2)
            self.assertAlmostEqual(summary["classes"][0]["mean_confidence"], 1.0)

    def test_multimodal_adapter_validates_but_does_not_use_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "tile.png"
            image_path.write_bytes(b"image")
            engine = FakeGufnetEngine()
            adapter = self._adapter(
                MultimodalGufnetAdapter,
                "multimodal_semantic_segmentation",
                root / "outputs",
                engine,
            )
            adapter.prepare()
            result = adapter.predict(
                "multimodal_01",
                {"image_path": str(image_path), "point_cloud_path": "tile.txt"},
            )
            self.assertFalse(result.metrics["image_used"])
            metadata = json.loads(
                Path(result.artifacts["projection_metadata"]).read_text(encoding="utf-8")
            )
            self.assertFalse(metadata["image_used"])
            summary = json.loads(
                Path(result.artifacts["class_summary"]).read_text(encoding="utf-8")
            )
            self.assertTrue(summary["image_validated"])
            self.assertFalse(summary["image_used"])
            self.assertEqual(engine.calls, ["tile.txt"])

    def test_engine_processes_all_points_in_order_across_chunks(self) -> None:
        engine = GufnetInferenceEngine(
            "checkpoint.ckpt", "config.yaml", "vendor/gufnet",
            device="cpu", max_chunk_points=3, min_chunk_points=1,
        )
        features = np.arange(42, dtype=np.float32).reshape(7, 6)
        engine.prepare = lambda: None
        engine.load_point_features = lambda _: features
        class FakeTorch:
            class OutOfMemoryError(RuntimeError):
                pass

            @staticmethod
            def inference_mode():
                return nullcontext()

        engine._torch = FakeTorch()
        engine._model = object()
        calls = []

        def predict_chunk(chunk):
            calls.append(chunk[:, 0].copy())
            labels = (chunk[:, 0] / 6).astype(np.int32) + 1
            probabilities = np.zeros((len(chunk), 15), dtype=np.float32)
            probabilities[np.arange(len(chunk)), labels - 1] = 1.0
            return labels, probabilities

        engine._predict_chunk = predict_chunk
        prediction = engine.predict("tile.las")

        self.assertEqual([len(chunk) for chunk in calls], [3, 3, 1])
        np.testing.assert_array_equal(prediction.point_labels, np.arange(1, 8))
        self.assertEqual(prediction.class_probabilities.shape, (7, 15))

    def test_engine_recenters_each_inference_chunk(self) -> None:
        engine = GufnetInferenceEngine(
            "checkpoint.ckpt", "config.yaml", "vendor/gufnet", device="cpu"
        )

        class FakeTensor:
            def __init__(self, value):
                self.value = value

            def to(self, _device):
                return self

        class FakeTorch:
            @staticmethod
            def from_numpy(value):
                return FakeTensor(value)

            @staticmethod
            def zeros(length, dtype=None, device=None):
                return np.zeros(length, dtype=np.int64)

            @staticmethod
            def ones(length, dtype=None, device=None):
                return np.ones(length, dtype=np.int64)

            long = np.int64

        class FakeOutput:
            ndim = 2
            shape = (2, 16)

            def __getitem__(self, _key):
                return self

        class FakeModel:
            def __call__(self, data):
                np.testing.assert_allclose(data["points"].value[:, :3].mean(axis=0), 0.0)
                raise RuntimeError("coordinates verified")

        engine._torch = FakeTorch()
        engine._model = FakeModel()
        features = np.asarray([[100, 200, 50, 1, 2, 3], [104, 202, 52, 4, 5, 6]], dtype=np.float32)
        with self.assertRaisesRegex(RuntimeError, "coordinates verified"):
            engine._predict_chunk(features)

    def test_multimodal_adapter_rejects_missing_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = FakeGufnetEngine()
            adapter = self._adapter(
                MultimodalGufnetAdapter,
                "multimodal_semantic_segmentation",
                Path(temp_dir),
                engine,
            )
            adapter.prepare()
            with self.assertRaisesRegex(FileNotFoundError, "Missing image"):
                adapter.predict(
                    "missing_image_01",
                    {"image_path": "missing.png", "point_cloud_path": "tile.txt"},
                )


if __name__ == "__main__":
    unittest.main()
