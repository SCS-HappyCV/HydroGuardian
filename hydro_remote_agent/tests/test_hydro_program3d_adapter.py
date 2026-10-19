from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from hydro_remote_agent.runtime.hydro_program3d_adapter import HydroProgram3DAdapter
from hydro_remote_agent.runtime.hydro_program3d_engine import (
    HydroProgram3DPrediction,
    infer_program_task_type,
    should_calibrate_no_target,
    visualization_preview_indices,
)
from hydro_remote_agent.runtime.quality_verification_adapter import verify_result
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"


class FakeHydroProgram3DEngine:
    def __init__(self) -> None:
        self.initialized = False
        self.calls = []

    def prepare(self) -> None:
        self.initialized = True

    def predict(self, image_path: str, point_cloud_path: str, query: str) -> HydroProgram3DPrediction:
        self.calls.append((image_path, point_cloud_path, query))
        return HydroProgram3DPrediction(
            target_mask=np.asarray([False, True, True, False]),
            target_probabilities=np.asarray([0.1, 0.8, 0.7, 0.2], dtype=np.float32),
            sample_indices=np.asarray([0, 2], dtype=np.int64),
            compiled_program={"selected_index": 0, "candidates": []},
            selected_program={"target": "ditch"},
            num_source_points=4,
            num_sampled_points=2,
            execution_confidence=0.82,
            abstained=False,
            no_target=False,
            device="cuda:0",
            geometry_used=True,
            selected_candidate_index=1,
            candidate_posterior_scores=(0.1, 0.8, 0.1),
            candidate_active_mask=(True, True, True),
            posterior_no_target_mass=0.1,
            abstain_probability=0.18,
            inferred_task_type="relation",
            applied_mask_threshold=0.05,
            model_no_target=False,
            calibrated_no_target=False,
        )

    def shutdown(self) -> None:
        self.initialized = False


class HydroProgram3DAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)

    def test_adapter_writes_source_coordinate_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            point_path = root / "tile.txt"
            np.savetxt(point_path, np.zeros((4, 7)))
            image_path = root / "tile.png"
            image_path.write_bytes(b"fake")
            engine = FakeHydroProgram3DEngine()
            adapter = HydroProgram3DAdapter(
                tool_spec=self.registry.get("language_guided_point_segmentation"),
                work_dir=root / "outputs",
                checkpoint_path="best.pth",
                engine=engine,
            )
            self.assertEqual(adapter.prepare().status, "ready")
            result = adapter.predict(
                "language_01",
                {
                    "image_path": str(image_path),
                    "point_cloud_path": str(point_path),
                    "query": "Find the ditch near the road.",
                },
            )
            self.assertFalse(result.is_mock)
            self.assertEqual(result.backend, "hydro_program3d_inference")
            self.assertEqual(result.metrics["num_points"], 4)
            self.assertEqual(result.metrics["selected_candidate_index"], 1)
            self.assertAlmostEqual(result.metrics["posterior_no_target_mass"], 0.1)
            self.assertEqual(result.metrics["inferred_task_type"], "relation")
            self.assertAlmostEqual(result.metrics["applied_mask_threshold"], 0.05)
            with np.load(result.artifacts["target_mask"], allow_pickle=False) as payload:
                np.testing.assert_array_equal(payload["target_mask"], [False, True, True, False])
            with np.load(result.artifacts["point_visualization"], allow_pickle=False) as payload:
                self.assertEqual(payload["positions"].shape, (4, 3))
                np.testing.assert_array_equal(payload["target_mask"], [False, True, True, False])
            metadata = json.loads(Path(result.artifacts["sampling_metadata"]).read_text(encoding="utf-8"))
            self.assertEqual(metadata["num_source_points"], 4)
            self.assertEqual(metadata["sample_indices"], [0, 2])
            program = json.loads(Path(result.artifacts["compiled_program"]).read_text(encoding="utf-8"))
            self.assertEqual(program["inference_diagnostics"]["candidate_active_mask"], [True, True, True])
            report = verify_result(
                {
                    "result_path": result.manifest_path,
                    "source_tool": "language_guided_point_segmentation",
                }
            )
            self.assertEqual(report["verdict"], "passed")

    def test_empty_unexplained_mask_warns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mask_path = root / "target_mask.npz"
            np.savez_compressed(mask_path, target_mask=np.zeros(3, dtype=np.bool_))
            probability_path = root / "target_probabilities.npz"
            np.savez_compressed(probability_path, target_probabilities=np.zeros(3, dtype=np.float32))
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps({
                    "tool": "language_guided_point_segmentation",
                    "status": "succeeded",
                    "is_mock": False,
                    "artifacts": {
                        "target_mask": str(mask_path),
                        "target_probabilities": str(probability_path),
                    },
                    "arguments": {},
                    "metrics": {"execution_confidence": 0.4, "no_target": False, "abstained": False},
                }),
                encoding="utf-8",
            )
            report = verify_result({"result_path": str(manifest_path), "source_tool": "language_guided_point_segmentation"})
            self.assertEqual(report["verdict"], "warning")
            self.assertTrue(report["abstention_recommended"])

    def test_program_task_type_and_no_target_calibration_are_task_aware(self) -> None:
        self.assertEqual(infer_program_task_type({"relations": [{"type": "near"}]}), "relation")
        self.assertEqual(infer_program_task_type({"attributes": ["thin"]}), "attribute")
        self.assertEqual(infer_program_task_type({"target": "shed"}), "class")
        self.assertTrue(
            should_calibrate_no_target("class", 0.06, 0.20, 0.051, 0.233)
        )
        self.assertFalse(
            should_calibrate_no_target("relation", 0.06, 0.20, 0.051, 0.233)
        )

    def test_visualization_preview_covers_scene_and_densifies_targets(self) -> None:
        mask = np.zeros(1000, dtype=np.bool_)
        mask[400:500] = True
        indices = visualization_preview_indices(mask, base_budget=100, target_budget=50)
        self.assertEqual(indices.dtype, np.uint32)
        self.assertEqual(indices[0], 0)
        self.assertEqual(indices[-1], 999)
        self.assertGreaterEqual(np.isin(indices, np.arange(400, 500)).sum(), 50)


if __name__ == "__main__":
    unittest.main()
