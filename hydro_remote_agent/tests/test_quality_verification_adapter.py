from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from hydro_remote_agent.runtime.quality_verification_adapter import (
    QualityVerificationAdapter,
    verify_result,
)
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"


def write_manifest(root: Path, tool: str, artifacts: dict, arguments: dict) -> Path:
    path = root / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "tool": tool,
                "status": "succeeded",
                "is_mock": False,
                "artifacts": {name: str(Path(value).resolve()) for name, value in artifacts.items()},
                "arguments": arguments,
            }
        ),
        encoding="utf-8",
    )
    return path


class QualityVerificationAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)

    def test_valid_segmentation_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            point_path = root / "points.txt"
            np.savetxt(point_path, np.zeros((4, 6)))
            labels_path = root / "labels.npz"
            np.savez_compressed(labels_path, point_labels=np.asarray([1, 4, 4, 13], dtype=np.int32))
            probabilities = np.full((4, 15), 0.01, dtype=np.float32)
            probabilities[np.arange(4), [0, 3, 3, 12]] = 0.86
            probabilities /= probabilities.sum(axis=1, keepdims=True)
            probability_path = root / "probabilities.npz"
            np.savez_compressed(probability_path, class_probabilities=probabilities)
            manifest = write_manifest(
                root,
                "point_semantic_segmentation",
                {"point_labels": labels_path, "class_probabilities": probability_path},
                {"point_cloud_path": str(point_path)},
            )
            report = verify_result(
                {
                    "result_path": str(manifest),
                    "source_tool": "point_semantic_segmentation",
                    "point_cloud_path": str(point_path),
                    "minimum_confidence": 0.6,
                }
            )
            self.assertEqual(report["verdict"], "passed")
            self.assertFalse(report["abstention_recommended"])

    def test_invalid_probabilities_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            labels_path = root / "labels.npz"
            np.savez_compressed(labels_path, point_labels=np.asarray([1, 2], dtype=np.int32))
            probability_path = root / "probabilities.npz"
            np.savez_compressed(
                probability_path,
                class_probabilities=np.asarray([[0.2] * 15, [np.nan] * 15]),
            )
            manifest = write_manifest(
                root,
                "point_semantic_segmentation",
                {"point_labels": labels_path, "class_probabilities": probability_path},
                {},
            )
            report = verify_result(
                {"result_path": str(manifest), "source_tool": "point_semantic_segmentation"}
            )
            self.assertEqual(report["verdict"], "failed")
            self.assertTrue(any(item["name"] == "probability_integrity" and item["status"] == "failed" for item in report["checks"]))

    def test_multimodal_segmentation_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            point_path = root / "points.txt"
            np.savetxt(point_path, np.zeros((4, 6)))
            labels_path = root / "labels.npz"
            np.savez_compressed(
                labels_path,
                point_labels=np.asarray([1, 4, 4, 13], dtype=np.int32),
            )
            probabilities = np.full((4, 15), 0.01, dtype=np.float32)
            probabilities[np.arange(4), [0, 3, 3, 12]] = 0.86
            probabilities /= probabilities.sum(axis=1, keepdims=True)
            probability_path = root / "probabilities.npz"
            np.savez_compressed(probability_path, class_probabilities=probabilities)
            manifest = write_manifest(
                root,
                "multimodal_semantic_segmentation",
                {
                    "point_labels": labels_path,
                    "class_probabilities": probability_path,
                },
                {"point_cloud_path": str(point_path)},
            )
            report = verify_result(
                {
                    "result_path": str(manifest),
                    "source_tool": "multimodal_semantic_segmentation",
                    "point_cloud_path": str(point_path),
                }
            )
            self.assertEqual(report["verdict"], "passed")

    def test_empty_change_result_recommends_abstention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "after.png"
            Image.new("RGB", (8, 6), "black").save(image_path)
            mask_path = root / "mask.png"
            Image.new("L", (8, 6), 0).save(mask_path)
            probability_path = root / "probability.npz"
            np.savez_compressed(probability_path, change_probability_map=np.zeros((6, 8), dtype=np.float32))
            regions_path = root / "regions.json"
            regions_path.write_text('{"regions": []}', encoding="utf-8")
            manifest = write_manifest(
                root,
                "image_change_detection",
                {
                    "change_mask": mask_path,
                    "change_probability_map": probability_path,
                    "change_regions": regions_path,
                },
                {"after_image_path": str(image_path)},
            )
            adapter = QualityVerificationAdapter(
                tool_spec=self.registry.get("result_quality_verification"),
                work_dir=root / "outputs",
            )
            adapter.prepare()
            result = adapter.predict(
                "verify_change",
                {"result_path": str(manifest), "source_tool": "image_change_detection"},
            )
            self.assertEqual(result.metrics["verdict"], "warning")
            self.assertTrue(result.metrics["abstention_recommended"])
            self.assertTrue(Path(result.artifacts["diagnostic_overlay"]).is_file())

    def test_change_verification_uses_materialized_cross_worker_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "after.png"
            Image.new("RGB", (8, 6), "black").save(image_path)
            mask_path = root / "mask.png"
            Image.new("L", (8, 6), 255).save(mask_path)
            probability_path = root / "probability.npz"
            np.savez_compressed(
                probability_path,
                change_probability_map=np.ones((6, 8), dtype=np.float32),
            )
            manifest = write_manifest(
                root,
                "image_change_detection",
                {
                    "change_mask": root / "stale-mask.png",
                    "change_probability_map": root / "stale-probability.npz",
                },
                {"after_image_path": str(root / "stale-after.png")},
            )
            report = verify_result(
                {
                    "result_path": str(manifest),
                    "source_tool": "image_change_detection",
                    "result_artifacts": {
                        "change_mask": str(mask_path),
                        "change_probability_map": str(probability_path),
                    },
                    "image_path": str(image_path),
                }
            )
            self.assertEqual(report["verdict"], "passed")


if __name__ == "__main__":
    unittest.main()
