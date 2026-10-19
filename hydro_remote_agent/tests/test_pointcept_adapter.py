import tempfile
import unittest
from pathlib import Path

import numpy as np

from hydro_remote_agent.runtime.pointcept_adapter import PointceptPtv3Adapter
from hydro_remote_agent.runtime.pointcept_engine import PointceptPrediction, PointceptPtv3InferenceEngine
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


ROOT = Path(__file__).resolve().parents[2]


class FakePointceptEngine:
    initialized = False

    def prepare(self) -> None:
        self.initialized = True

    def predict(self, path):
        probabilities = np.zeros((3, 15), dtype=np.float32)
        probabilities[0, 0] = 1.0
        probabilities[1:, 12] = 1.0
        return PointceptPrediction(
            point_labels=np.asarray([1, 13, 13], dtype=np.int32),
            class_probabilities=probabilities,
            num_points=3,
            device="cpu",
            sample_id="00_000004",
            checkpoint_epoch=19,
        )


class PointceptAdapterTest(unittest.TestCase):
    def test_engine_records_explicit_split_root(self) -> None:
        engine = PointceptPtv3InferenceEngine(
            checkpoint_path="checkpoint.pth",
            config_path="config.py",
            vendor_root="pointcept",
            device="cpu",
            split="val",
            split_root="primary_split",
        )
        self.assertEqual(engine.split, "val")
        self.assertEqual(engine.split_root.name, "primary_split")

    def test_sample_id_requires_wcs_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "00" / "velodyne" / "000004.txt"
            path.parent.mkdir(parents=True)
            path.write_text("0 0 0 0 0 0 1\n", encoding="utf-8")
            self.assertEqual(PointceptPtv3InferenceEngine.sample_id_from_path(path), "00_000004")

    def test_adapter_writes_original_point_artifacts(self) -> None:
        registry = load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml")
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = PointceptPtv3Adapter(
                tool_spec=registry.get("point_semantic_segmentation"),
                work_dir=Path(temp_dir),
                enabled=True,
                checkpoint_path="checkpoint.pth",
                config_path="config.py",
                vendor_root="pointcept",
                device="cpu",
                engine=FakePointceptEngine(),
            )
            self.assertEqual(adapter.prepare().status, "ready")
            result = adapter.predict(
                "ptv3_01",
                {"point_cloud_path": "tile.txt", "target_class_ids": [13]},
            )
            self.assertEqual(result.backend, "pointcept_ptv3_inference")
            self.assertEqual(result.metrics["num_points"], 3)
            with np.load(result.artifacts["point_labels"]) as payload:
                np.testing.assert_array_equal(payload["point_labels"], [1, 13, 13])
            with np.load(result.artifacts["class_masks"]) as payload:
                self.assertEqual(payload["class_masks"].shape, (1, 3))

    def test_adapter_replays_zero_based_prediction_cache_without_preparing_engine(self) -> None:
        registry = load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            point_path = root / "00" / "velodyne" / "000004.txt"
            point_path.parent.mkdir(parents=True)
            point_path.write_text("0 0 0 0 0 0 1\n", encoding="utf-8")
            cache_dir = root / "cache"
            cache_dir.mkdir()
            np.save(cache_dir / "00_000004_pred.npy", np.asarray([0, 12, 12]))
            engine = FakePointceptEngine()
            adapter = PointceptPtv3Adapter(
                tool_spec=registry.get("point_semantic_segmentation"),
                work_dir=root / "outputs",
                enabled=True,
                checkpoint_path="checkpoint.pth",
                config_path="config.py",
                vendor_root="pointcept",
                prediction_cache_dir=cache_dir,
                cache_labels_zero_based=True,
                engine=engine,
            )

            self.assertEqual(adapter.prepare().status, "ready")
            self.assertFalse(engine.initialized)
            result = adapter.predict("cached_01", {"point_cloud_path": str(point_path)})

            self.assertEqual(result.metrics["prediction_source"], "cache")
            with np.load(result.artifacts["point_labels"]) as payload:
                np.testing.assert_array_equal(payload["point_labels"], [1, 13, 13])

    def test_adapter_writes_online_prediction_to_restart_cache(self) -> None:
        registry = load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_cache = root / "write_cache"
            point_path = root / "00" / "velodyne" / "000004.txt"
            point_path.parent.mkdir(parents=True)
            point_path.write_text("0 0 0 0 0 0 1\n", encoding="utf-8")
            adapter = PointceptPtv3Adapter(
                tool_spec=registry.get("point_semantic_segmentation"),
                work_dir=root / "outputs",
                enabled=True,
                checkpoint_path="checkpoint.pth",
                config_path="config.py",
                vendor_root="pointcept",
                prediction_write_cache_dir=write_cache,
                cache_labels_zero_based=True,
                engine=FakePointceptEngine(),
            )
            adapter.prepare()
            adapter.predict("online_01", {"point_cloud_path": str(point_path)})
            np.testing.assert_array_equal(
                np.load(write_cache / "00_000004_pred.npy"), [0, 12, 12]
            )


if __name__ == "__main__":
    unittest.main()
