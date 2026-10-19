from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hydro_remote_agent.runtime import (
    ExpertConfigurationError,
    ExpertNotReadyError,
    build_mock_runtime,
    load_expert_runtime,
)
from hydro_remote_agent.schemas.tool_spec import ToolArgumentError, ToolRegistry, load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"
RUNTIME_PATH = PACKAGE_ROOT / "configs" / "expert_runtime.yaml"


class ExpertRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)

    def test_config_registers_real_and_mock_experts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = load_expert_runtime(RUNTIME_PATH, self.registry, work_dir=temp_dir)
            health = runtime.health_check()
            self.assertEqual({item.tool for item in health}, set(self.registry.names()))
            backends = {item.tool: item.backend for item in health}
            self.assertEqual(backends["geometry_relation_analysis"], "geometry_numpy")
            self.assertEqual(backends["point_semantic_segmentation"], "gufnet_3d_inference")
            gufnet_engine = runtime.get_adapter("point_semantic_segmentation").engine
            self.assertEqual(gufnet_engine.max_chunk_points, 100000)
            self.assertEqual(gufnet_engine.min_chunk_points, 12500)
            self.assertEqual(backends["image_change_detection"], "rfanet_change_detection")
            self.assertEqual(
                backends["result_quality_verification"],
                "deterministic_quality_verification",
            )
            self.assertEqual(
                backends["language_guided_point_segmentation"],
                "hydro_program3d_inference",
            )
            self.assertNotIn("mock", backends.values())
            language_engine = runtime.get_adapter("language_guided_point_segmentation").engine
            self.assertEqual(
                language_engine.mask_thresholds,
                {"class": 0.3, "attribute": 0.03, "relation": 0.05},
            )
            self.assertAlmostEqual(language_engine.no_target_posterior_threshold, 0.06605950832366944)
            self.assertTrue(all(item.status == "not_ready" for item in health))

    def test_command_line_work_dir_override_resolves_from_current_directory(self) -> None:
        runtime = load_expert_runtime(RUNTIME_PATH, self.registry, work_dir="runtime_override")
        adapter = runtime.get_adapter("point_semantic_segmentation")
        self.assertEqual(adapter.work_dir.parent, (Path.cwd() / "runtime_override").resolve())

    def test_prepare_makes_all_experts_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = build_mock_runtime(self.registry, temp_dir)
            health = runtime.prepare()
            self.assertEqual(len(health), 6)
            self.assertTrue(all(item.status == "ready" for item in health))
            runtime.shutdown()
            self.assertTrue(all(item.status == "not_ready" for item in runtime.health_check()))

    def test_invoke_requires_prepared_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = build_mock_runtime(self.registry, temp_dir)
            with self.assertRaises(ExpertNotReadyError):
                runtime.invoke(
                    "point_semantic_segmentation",
                    {"point_cloud_path": "tile.txt"},
                    invocation_id="not_ready_01",
                )

    def test_invoke_validates_tool_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = build_mock_runtime(self.registry, temp_dir)
            runtime.prepare("image_change_detection")
            with self.assertRaises(ToolArgumentError):
                runtime.invoke(
                    "image_change_detection",
                    {"before_image_path": "before.png"},
                    invocation_id="invalid_args_01",
                )

    def test_mock_invocation_writes_manifest_and_contract_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = build_mock_runtime(self.registry, temp_dir)
            runtime.prepare("point_semantic_segmentation")
            result = runtime.invoke(
                "point_semantic_segmentation",
                {"point_cloud_path": "tile.txt"},
                invocation_id="segment_01",
            )
            tool = self.registry.get("point_semantic_segmentation")
            self.assertEqual(result.status, "succeeded")
            self.assertTrue(result.is_mock)
            self.assertEqual(set(result.artifacts), set(tool.output.artifacts))
            self.assertTrue(Path(result.manifest_path).is_file())
            self.assertTrue(all(Path(path).is_file() for path in result.artifacts.values()))
            with Path(result.manifest_path).open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            self.assertEqual(manifest["backend"], "mock")
            self.assertTrue(manifest["is_mock"])
            self.assertEqual(manifest["arguments"]["point_cloud_path"], "tile.txt")

    def test_runtime_config_rejects_missing_expert(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "runtime.yaml"
            config_path.write_text(
                'schema_version: "1.0"\nexperts:\n  point_semantic_segmentation:\n'
                "    backend: mock\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ExpertConfigurationError, "Missing adapters"):
                load_expert_runtime(config_path, self.registry, work_dir=temp_dir)

    def test_disabled_expert_reports_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_text = RUNTIME_PATH.read_text(encoding="utf-8").replace(
                "point_semantic_segmentation:\n    backend: gufnet_3d_inference\n    enabled: true",
                "point_semantic_segmentation:\n    backend: gufnet_3d_inference\n    enabled: false",
            )
            config_path = Path(temp_dir) / "runtime.yaml"
            config_path.write_text(config_text, encoding="utf-8")
            runtime = load_expert_runtime(config_path, self.registry, work_dir=temp_dir)
            health = runtime.prepare("point_semantic_segmentation")[0]
            self.assertEqual(health.status, "disabled")
            with self.assertRaises(ExpertNotReadyError):
                runtime.invoke(
                    "point_semantic_segmentation",
                    {"point_cloud_path": "tile.txt"},
                    invocation_id="disabled_01",
                )

    def test_subset_registry_ignores_unselected_disabled_experts(self) -> None:
        selected = ToolRegistry(
            schema_version=self.registry.schema_version,
            tools=(self.registry.get("geometry_relation_analysis"),),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "runtime.yaml"
            config_path.write_text(
                'schema_version: "1.0"\nexperts:\n'
                "  point_semantic_segmentation:\n"
                "    backend: mock\n"
                "    enabled: false\n"
                "  geometry_relation_analysis:\n"
                "    backend: geometry_numpy\n"
                "    enabled: true\n",
                encoding="utf-8",
            )

            runtime = load_expert_runtime(config_path, selected, work_dir=temp_dir)

            self.assertEqual(runtime.registry.names(), ("geometry_relation_analysis",))
            self.assertEqual(
                runtime.health_check("geometry_relation_analysis")[0].backend,
                "geometry_numpy",
            )

    def test_subset_registry_rejects_unselected_enabled_expert(self) -> None:
        selected = ToolRegistry(
            schema_version=self.registry.schema_version,
            tools=(self.registry.get("geometry_relation_analysis"),),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "runtime.yaml"
            config_path.write_text(
                'schema_version: "1.0"\nexperts:\n'
                "  point_semantic_segmentation:\n"
                "    backend: mock\n"
                "    enabled: true\n"
                "  geometry_relation_analysis:\n"
                "    backend: geometry_numpy\n"
                "    enabled: true\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ExpertConfigurationError, "Unknown configured expert"):
                load_expert_runtime(config_path, selected, work_dir=temp_dir)

    def test_geometry_backend_is_rejected_for_other_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_text = RUNTIME_PATH.read_text(encoding="utf-8").replace(
                "point_semantic_segmentation:\n    backend: gufnet_3d_inference",
                "point_semantic_segmentation:\n    backend: geometry_numpy",
            )
            config_path = Path(temp_dir) / "runtime.yaml"
            config_path.write_text(config_text, encoding="utf-8")
            with self.assertRaisesRegex(ExpertConfigurationError, "can only serve"):
                load_expert_runtime(config_path, self.registry, work_dir=temp_dir)


if __name__ == "__main__":
    unittest.main()
