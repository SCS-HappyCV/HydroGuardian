from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from hydro_remote_agent.runtime.geometry_adapter import (
    GeometryRelationAdapter,
    execute_geometry_operation,
    load_segmentation_labels,
)
from hydro_remote_agent.runtime import load_expert_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"
RUNTIME_PATH = PACKAGE_ROOT / "configs" / "expert_runtime.yaml"


class GeometryAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)
        self.xyz = np.asarray(
            [
                [0.0, 0.0, 3.0],
                [1.0, 0.0, 1.0],
                [10.0, 0.0, 4.0],
                [0.0, 1.0, 0.0],
                [10.0, 4.0, 2.0],
                [30.0, 30.0, 0.0],
            ],
            dtype=np.float64,
        )
        self.labels = np.asarray([4, 4, 4, 13, 13, 2], dtype=np.int32)

    def _arguments(self, operation: str) -> dict:
        return {
            "operation": operation,
            "target_class_id": 4,
            "reference_class_id": 13,
        }

    def test_near_uses_horizontal_euclidean_threshold(self) -> None:
        arguments = self._arguments("near")
        arguments["distance_threshold_m"] = 3.0
        mask, report, arrays = execute_geometry_operation(self.xyz, self.labels, arguments)
        np.testing.assert_array_equal(mask, [True, True, False, False, False, False])
        np.testing.assert_allclose(arrays["target_horizontal_distance_m"], [1.0, 2**0.5, 4.0])
        self.assertEqual(report["result"]["point_count"], 2)
        self.assertAlmostEqual(report["selected_target_ratio"], 2 / 3)

    def test_above_uses_reference_median_elevation(self) -> None:
        arguments = self._arguments("above")
        arguments["z_margin_m"] = 1.0
        mask, report, _ = execute_geometry_operation(self.xyz, self.labels, arguments)
        np.testing.assert_array_equal(mask, [True, False, True, False, False, False])
        self.assertEqual(report["reference_median_elevation_m"], 1.0)

    def test_class_statistics_does_not_require_reference(self) -> None:
        mask, report, arrays = execute_geometry_operation(
            self.xyz,
            self.labels,
            {"operation": "class_statistics", "target_class_id": 4},
        )
        np.testing.assert_array_equal(mask, self.labels == 4)
        self.assertEqual(report["target"]["point_count"], 3)
        self.assertEqual(arrays, {})

    def test_pair_distance_and_elevation_difference_report_values(self) -> None:
        distance_mask, distance_report, distance_arrays = execute_geometry_operation(
            self.xyz, self.labels, self._arguments("pair_distance")
        )
        np.testing.assert_array_equal(distance_mask, self.labels == 4)
        self.assertIn("spatial_distance_m", distance_report)
        self.assertEqual(len(distance_arrays["target_spatial_distance_m"]), 3)

        elevation_mask, elevation_report, elevation_arrays = execute_geometry_operation(
            self.xyz, self.labels, self._arguments("elevation_difference")
        )
        np.testing.assert_array_equal(elevation_mask, self.labels == 4)
        np.testing.assert_allclose(
            elevation_arrays["target_elevation_difference_m"], [2.0, 0.0, 3.0]
        )
        self.assertEqual(elevation_report["elevation_difference_m"]["median"], 2.0)

    def test_probability_input_maps_zero_based_channels_to_raw_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probabilities = np.zeros((3, 15), dtype=np.float32)
            probabilities[0, 3] = 1.0
            probabilities[1, 12] = 1.0
            probabilities[2, 0] = 1.0
            path = Path(temp_dir) / "probabilities.npz"
            np.savez_compressed(path, class_probabilities=probabilities)
            np.testing.assert_array_equal(load_segmentation_labels(path), [4, 13, 1])

    def test_existing_pred_labels_are_mapped_from_zero_based_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "prediction.npz"
            np.savez_compressed(path, pred_labels=np.asarray([3, 12, 0], dtype=np.int32))
            np.testing.assert_array_equal(load_segmentation_labels(path), [4, 13, 1])

    def test_adapter_writes_real_npz_report_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            point_path = root / "points.npy"
            labels_path = root / "labels.npz"
            np.save(point_path, self.xyz)
            np.savez_compressed(labels_path, point_labels=self.labels)
            adapter = GeometryRelationAdapter(
                tool_spec=self.registry.get("geometry_relation_analysis"),
                work_dir=root / "outputs",
            )
            self.assertEqual(adapter.prepare().status, "ready")
            result = adapter.predict(
                "geometry_real_01",
                {
                    "point_cloud_path": str(point_path),
                    "segmentation_result_path": str(labels_path),
                    "operation": "near",
                    "target_class_id": 4,
                    "reference_class_id": 13,
                    "distance_threshold_m": 3.0,
                },
            )
            self.assertFalse(result.is_mock)
            self.assertEqual(result.backend, "geometry_numpy")
            self.assertEqual(result.metrics["selected_points"], 2)
            with np.load(result.artifacts["relation_mask"], allow_pickle=False) as payload:
                np.testing.assert_array_equal(
                    payload["relation_mask"], [True, True, False, False, False, False]
                )
                np.testing.assert_array_equal(payload["point_indices"], [0, 1])
            report = json.loads(Path(result.artifacts["geometry_report"]).read_text(encoding="utf-8"))
            manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(report["operation"], "near")
            self.assertFalse(manifest["is_mock"])

    def test_configured_runtime_invokes_real_geometry_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            point_path = root / "points.npy"
            labels_path = root / "labels.npy"
            np.save(point_path, self.xyz)
            np.save(labels_path, self.labels)
            runtime = load_expert_runtime(RUNTIME_PATH, self.registry, work_dir=root / "outputs")
            runtime.prepare("geometry_relation_analysis")
            result = runtime.invoke(
                "geometry_relation_analysis",
                {
                    "point_cloud_path": str(point_path),
                    "segmentation_result_path": str(labels_path),
                    "operation": "class_statistics",
                    "target_class_id": 4,
                },
                invocation_id="configured_geometry_01",
            )
            self.assertEqual(result.backend, "geometry_numpy")
            self.assertFalse(result.is_mock)
            self.assertEqual(result.metrics["selected_points"], 3)

    def test_count_mismatch_is_rejected_and_missing_reference_is_structured(self) -> None:
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            execute_geometry_operation(self.xyz, self.labels[:-1], self._arguments("near"))
        missing_reference_labels = np.where(self.labels == 13, 2, self.labels)
        mask, report, arrays = execute_geometry_operation(
            self.xyz, missing_reference_labels, self._arguments("near")
        )
        self.assertFalse(mask.any())
        self.assertEqual(report["outcome"], "no_reference")
        self.assertEqual(arrays, {})

    def test_empty_target_is_a_structured_outcome(self) -> None:
        missing_target_labels = np.where(self.labels == 4, 2, self.labels)
        mask, report, arrays = execute_geometry_operation(
            self.xyz, missing_target_labels, self._arguments("above")
        )
        self.assertEqual(mask.dtype, np.bool_)
        self.assertEqual(len(mask), len(self.xyz))
        self.assertFalse(mask.any())
        self.assertEqual(report["outcome"], "no_target")
        self.assertEqual(report["result"]["point_count"], 0)
        self.assertEqual(arrays, {})

    def test_adapter_persists_structured_empty_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            point_path = root / "points.npy"
            labels_path = root / "labels.npy"
            np.save(point_path, self.xyz)
            np.save(labels_path, np.where(self.labels == 4, 2, self.labels))
            adapter = GeometryRelationAdapter(
                tool_spec=self.registry.get("geometry_relation_analysis"),
                work_dir=root / "outputs",
            )
            adapter.prepare()
            result = adapter.predict(
                "geometry_empty_01",
                {
                    "point_cloud_path": str(point_path),
                    "segmentation_result_path": str(labels_path),
                    "operation": "near",
                    "target_class_id": 4,
                    "reference_class_id": 13,
                },
            )
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(result.metrics["outcome"], "no_target")
            self.assertIn("intentionally empty", result.warnings[0])
            with np.load(result.artifacts["relation_mask"], allow_pickle=False) as payload:
                self.assertFalse(payload["relation_mask"].any())


if __name__ == "__main__":
    unittest.main()
