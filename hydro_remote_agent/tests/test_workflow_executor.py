from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Mapping

from hydro_remote_agent.runtime import ExpertNotReadyError, build_mock_runtime
from hydro_remote_agent.runtime.mock_adapter import MockExpertAdapter
from hydro_remote_agent.schemas.agent_action import AgentRequest, load_agent_request
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.workflow import AgentExecutor, WorkflowExecutor
from hydro_remote_agent.tools.execute_workflow import main as execute_workflow_main


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"
WORKFLOW_PATH = PACKAGE_ROOT / "examples" / "agent_actions" / "workflow.json"
RUNTIME_PATH = PACKAGE_ROOT / "configs" / "expert_runtime.yaml"


class FailingMockAdapter(MockExpertAdapter):
    def predict(self, invocation_id: str, arguments: Mapping[str, Any]):
        raise RuntimeError("Injected expert failure")


class WarningMockAdapter(MockExpertAdapter):
    def predict(self, invocation_id: str, arguments: Mapping[str, Any]):
        result = super().predict(invocation_id, arguments)
        object.__setattr__(result, "warnings", ("Quality verification recommends abstention.",))
        return result


class WorkflowExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)

    def test_workflow_resolves_artifact_and_runs_auto_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = build_mock_runtime(self.registry, root / "experts")
            request = load_agent_request(WORKFLOW_PATH, self.registry)
            result = WorkflowExecutor(runtime, root / "workflows").execute(
                request, execution_id="relation_01"
            )
            self.assertEqual(result.status, "succeeded")
            self.assertTrue(result.is_mock)
            self.assertTrue(Path(result.manifest_path).is_file())
            segment, relation = result.steps
            self.assertIsNotNone(segment.verification_result)
            self.assertIsNotNone(relation.verification_result)
            resolved_path = relation.resolved_arguments["segmentation_result_path"]
            self.assertEqual(resolved_path, segment.result.artifacts["point_labels"])
            self.assertNotIn("${", resolved_path)
            self.assertEqual(set(result.terminal_artifacts), {"relation_mask", "geometry_report"})

    def test_skip_policy_does_not_prepare_or_run_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
            for step in payload["action"]["steps"]:
                step["verification"] = "skip"
            request = AgentRequest.from_dict(payload, self.registry)
            runtime = build_mock_runtime(self.registry, root / "experts")
            result = WorkflowExecutor(runtime, root / "workflows").execute(
                request, execution_id="skip_verify_01"
            )
            self.assertIsNone(result.steps[0].verification_result)
            verifier_health = runtime.health_check("result_quality_verification")[0]
            self.assertEqual(verifier_health.status, "not_ready")

    def test_workflow_propagates_verifier_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = build_mock_runtime(self.registry, root / "experts")
            verifier = runtime.get_adapter("result_quality_verification")
            runtime._adapters["result_quality_verification"] = WarningMockAdapter(
                tool_spec=verifier.tool_spec,
                work_dir=verifier.work_dir,
            )
            request = load_agent_request(WORKFLOW_PATH, self.registry)
            result = WorkflowExecutor(runtime, root / "workflows").execute(
                request, execution_id="warning_verify_01"
            )
            self.assertIn("Quality verification recommends abstention.", result.warnings)

    def test_failure_skips_dependents_but_runs_independent_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = {
                "schema_version": "1.0",
                "request_id": "failure_branches_01",
                "intent": "multi_branch_analysis",
                "action": {
                    "type": "workflow",
                    "steps": [
                        {
                            "step_id": "segment",
                            "tool": "point_semantic_segmentation",
                            "arguments": {"point_cloud_path": "tile.txt"},
                            "verification": "skip",
                        },
                        {
                            "step_id": "relation",
                            "tool": "geometry_relation_analysis",
                            "depends_on": ["segment"],
                            "arguments": {
                                "point_cloud_path": "tile.txt",
                                "segmentation_result_path": "${segment.artifacts.point_labels}",
                                "operation": "class_statistics",
                                "target_class_id": 4,
                            },
                        },
                        {
                            "step_id": "change",
                            "tool": "image_change_detection",
                            "arguments": {
                                "before_image_path": "before.png",
                                "after_image_path": "after.png",
                            },
                            "verification": "skip",
                        },
                    ],
                },
            }
            request = AgentRequest.from_dict(payload, self.registry)
            runtime = build_mock_runtime(self.registry, root / "experts")
            runtime._adapters["point_semantic_segmentation"] = FailingMockAdapter(
                tool_spec=self.registry.get("point_semantic_segmentation"),
                work_dir=root / "experts" / "point_semantic_segmentation",
            )
            result = WorkflowExecutor(runtime, root / "workflows").execute(
                request, execution_id="failure_01"
            )
            self.assertEqual(result.status, "failed")
            self.assertEqual([step.status for step in result.steps], ["failed", "skipped", "succeeded"])
            self.assertEqual(result.steps[1].error.code, "dependency_failed")
            self.assertIn("change.change_mask", result.terminal_artifacts)

            agent_result = AgentExecutor(runtime, root / "agent").execute(
                request, execution_id="agent_failure_01", skip_mock=False
            )
            self.assertEqual(agent_result.error.code, "step_execution_failed")
            self.assertEqual(agent_result.error.details["step_id"], "segment")
            self.assertEqual(agent_result.error.details["tool"], "point_semantic_segmentation")
            self.assertIn("Injected expert failure", agent_result.error.message)

    def test_executor_rejects_non_workflow_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            request = AgentRequest.from_dict(
                {
                    "schema_version": "1.0",
                    "request_id": "direct_01",
                    "intent": "information",
                    "action": {"type": "direct_answer", "answer": "answer"},
                },
                self.registry,
            )
            runtime = build_mock_runtime(self.registry, Path(temp_dir) / "experts")
            with self.assertRaisesRegex(TypeError, "only accepts"):
                WorkflowExecutor(runtime, Path(temp_dir) / "workflows").execute(request)

    def test_executor_rejects_excessively_long_execution_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            request = load_agent_request(WORKFLOW_PATH, self.registry)
            runtime = build_mock_runtime(self.registry, Path(temp_dir) / "experts")
            with self.assertRaisesRegex(ValueError, "at most 64"):
                WorkflowExecutor(runtime, Path(temp_dir) / "workflows").execute(
                    request, execution_id="e" * 65
                )

    def test_disabled_required_expert_becomes_failed_step(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = build_mock_runtime(self.registry, root / "experts")
            runtime.get_adapter("multimodal_semantic_segmentation").enabled = False
            request = load_agent_request(WORKFLOW_PATH, self.registry)
            result = WorkflowExecutor(runtime, root / "workflows").execute(
                request, execution_id="disabled_01"
            )
            self.assertEqual(result.steps[0].status, "failed")
            self.assertIn("ExpertNotReadyError", result.steps[0].error.message)
            self.assertEqual(result.steps[1].status, "skipped")

    def test_workflow_cli_runs_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime_path = root / "mock_runtime.yaml"
            runtime_text = RUNTIME_PATH.read_text(encoding="utf-8")
            runtime_text = runtime_text.replace("backend: geometry_numpy", "backend: mock")
            runtime_text = runtime_text.replace("backend: gufnet_3d_inference", "backend: mock")
            runtime_path.write_text(runtime_text, encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                execute_workflow_main(
                    [
                        str(WORKFLOW_PATH),
                        "--registry",
                        str(REGISTRY_PATH),
                        "--runtime",
                        str(runtime_path),
                        "--expert-work-dir",
                        str(root / "experts"),
                        "--workflow-work-dir",
                        str(root / "workflows"),
                        "--execution-id",
                        "cli_relation_01",
                    ]
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["status"], "succeeded")
            self.assertEqual(payload["execution_id"], "cli_relation_01")
            self.assertTrue(Path(payload["manifest_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
