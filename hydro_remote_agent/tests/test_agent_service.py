from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Mapping

from hydro_remote_agent.runtime import build_mock_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.service.contracts import JobSubmission
from hydro_remote_agent.service.store import JobStore
from hydro_remote_agent.service.worker import ExecutorWorker, PlannerWorker
from hydro_remote_agent.service.worker import _execution_attempt, _is_transient_expert_error
from hydro_remote_agent.tools.agent_service_worker import build_parser
from hydro_remote_agent.service.planner import (
    _first_json_object,
    calibrate_planner_payload,
    online_planner_record,
)
from hydro_remote_agent.workflow import AgentExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PACKAGE_ROOT / "configs" / "tool_registry.yaml"


class StaticPlanner:
    def __init__(self, plan: Mapping[str, Any]) -> None:
        self._plan = dict(plan)

    def plan(self, submission: Mapping[str, Any]) -> Dict[str, Any]:
        return dict(self._plan)


class AgentServiceTest(unittest.TestCase):
    def test_worker_parser_accepts_lease_seconds(self) -> None:
        args = build_parser().parse_args(
            ["executor", "--db", "jobs.sqlite", "--lease-seconds", "120"]
        )
        self.assertEqual(args.lease_seconds, 120.0)

    def test_transient_expert_disconnect_is_detected(self) -> None:
        self.assertTrue(
            _is_transient_expert_error(
                RuntimeError("HTTP 503: No online worker supports tool")
            )
        )
        self.assertFalse(_is_transient_expert_error(ValueError("invalid arguments")))

    def test_execution_attempt_ignores_planner_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            job = store.create_job(JobSubmission("request:attempt", "query", {}))
            store.claim("planning", "planner")
            self.assertEqual(_execution_attempt(store, job.job_id), 1)
            store.transition(
                job.job_id,
                "planning",
                "queued_execution",
                plan=self._direct_plan("request:attempt"),
                event_type="planning_succeeded",
            )
            store.claim("execution", "executor")
            store.transition(
                job.job_id,
                "executing",
                "queued_execution",
                error={"code": "execution_retry"},
                event_type="execution_retry",
            )
            self.assertEqual(_execution_attempt(store, job.job_id), 2)

    def setUp(self) -> None:
        self.registry = load_tool_registry(REGISTRY_PATH)

    @staticmethod
    def _direct_plan(request_id: str) -> Dict[str, Any]:
        return {
            "schema_version": "1.0",
            "request_id": request_id,
            "intent": "information",
            "action": {"type": "direct_answer", "answer": "present"},
            "expected_output": {"type": "text", "coordinate_space": "none"},
        }

    def test_idempotent_creation_claim_and_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            submission = JobSubmission("request:1", "query", {"image_path": "tile.png"})
            first = store.create_job(submission, "same-key")
            second = store.create_job(submission, "same-key")
            self.assertEqual(first.job_id, second.job_id)
            claimed = store.claim("planning", "worker-1", lease_seconds=10)
            self.assertEqual(claimed.job_id, first.job_id)
            self.assertEqual(claimed.status, "planning")
            self.assertEqual([event["event_type"] for event in store.events(first.job_id)], ["created", "claimed"])

    def test_step_progress_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            job = store.create_job(JobSubmission("request:step", "query", {}, planned_request=self._direct_plan("request:step")))
            step = store.upsert_step("task-1", job.job_id, "point_semantic_segmentation", status="running", progress=0.5, phase="inference")
            self.assertEqual(step.progress, 0.5)
            self.assertEqual(store.steps(job.job_id)[0].phase, "inference")
            self.assertEqual(store.record_event(job.job_id, "step_progress", step.to_dict())["event_type"], "step_progress")

    def test_expired_job_marks_only_its_steps_lost(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            first = store.create_job(JobSubmission("request:lost-1", "query", {}))
            second = store.create_job(JobSubmission("request:lost-2", "query", {}))
            store.upsert_step("step-lost", first.job_id, "tool", status="running", worker_id="dead")
            store.upsert_step("step-live", second.job_id, "tool", status="running", worker_id="live")
            store.claim("planning", "dead-worker", lease_seconds=1)
            self.assertEqual(store.recover_expired(now=10**12), 1)
            self.assertEqual(store.step("step-lost").status, "lost")
            self.assertEqual(store.step("step-live").status, "running")

    def test_processed_message_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            self.assertTrue(store.claim_message("msg-1", "worker", "progress"))
            self.assertFalse(store.claim_message("msg-1", "worker", "progress"))

    def test_lost_steps_are_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            job = store.create_job(JobSubmission("request:recover", "query", {}))
            store.upsert_step("step-recover", job.job_id, "tool", status="lost", attempt=2, arguments={"x": 1})
            self.assertEqual(store.recoverable_steps()[0].attempt, 2)

    def test_expired_lease_returns_job_to_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            job = store.create_job(JobSubmission("request:2", "query", {}))
            store.claim("planning", "dead-worker", lease_seconds=1)
            self.assertEqual(store.recover_expired(now=10**12), 1)
            recovered = store.require(job.job_id)
            self.assertEqual(recovered.status, "queued_planning")
            self.assertIsNone(recovered.lease_owner)

    def test_cancel_and_retry_follow_terminal_state_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JobStore(Path(temp_dir) / "jobs.sqlite")
            queued = store.create_job(JobSubmission("request:cancel", "query", {}))
            self.assertEqual(store.cancel(queued.job_id).status, "cancelled")

            plan = self._direct_plan("request:retry")
            blocked = store.create_job(
                JobSubmission("request:retry", "query", {}, planned_request=plan)
            )
            store.claim("execution", "worker")
            store.transition(
                blocked.job_id,
                "executing",
                "blocked_expert",
                error={"code": "not_ready"},
            )
            retried = store.retry(blocked.job_id)
            self.assertEqual(retried.status, "queued_execution")
            self.assertIsNone(retried.error)
            self.assertEqual(store.events(blocked.job_id)[-1]["event_type"], "retried")

    def test_planner_and_executor_workers_complete_direct_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JobStore(root / "jobs.sqlite")
            job = store.create_job(JobSubmission("request:3", "query", {}))
            planner = PlannerWorker(
                store,
                StaticPlanner(self._direct_plan("request:3")),
                self.registry,
                worker_id="planner-test",
            )
            self.assertTrue(planner.run_once())
            self.assertEqual(store.require(job.job_id).status, "queued_execution")
            runtime = build_mock_runtime(self.registry, root / "experts")
            executor = ExecutorWorker(
                store,
                AgentExecutor(runtime, root / "executions"),
                self.registry,
                worker_id="executor-test",
            )
            self.assertTrue(executor.run_once())
            completed = store.require(job.job_id)
            self.assertEqual(completed.status, "succeeded")
            self.assertEqual(completed.result["execution_mode"], "planner_only")
            self.assertEqual(completed.result["outcome"], "response")

    def test_mock_expert_is_blocked_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = JobStore(root / "jobs.sqlite")
            request_id = "request:4"
            plan = {
                "schema_version": "1.0",
                "request_id": request_id,
                "intent": "attribute_segmentation",
                "action": {
                    "type": "tool_call",
                    "tool": "language_guided_point_segmentation",
                    "arguments": {
                        "image_path": "tile.png",
                        "point_cloud_path": "tile.txt",
                        "query": "segment target",
                    },
                    "verification": "required",
                },
                "expected_output": {
                    "type": "point_mask",
                    "coordinate_space": "source_point_cloud",
                },
            }
            job = store.create_job(
                JobSubmission(request_id, "query", {}, planned_request=plan)
            )
            runtime = build_mock_runtime(self.registry, root / "experts")
            worker = ExecutorWorker(
                store,
                AgentExecutor(runtime, root / "executions"),
                self.registry,
            )
            worker.run_once()
            blocked = store.require(job.job_id)
            self.assertEqual(blocked.status, "blocked_expert")
            self.assertEqual(blocked.error["code"], "expert_not_deployed")
            self.assertIn("language_guided_point_segmentation", blocked.error["tools"])

    def test_online_planner_prompt_contains_frozen_class_mapping(self) -> None:
        record = online_planner_record(
            {
                "request_id": "request:ontology",
                "query": "find Cementroad",
                "language": "en",
                "assets": {"image_path": "tile.png"},
            },
            self.registry,
        )
        system_prompt = record["messages"][0]["content"]
        self.assertIn('"3":"Cementroad"', system_prompt)
        self.assertIn('"13":"Waterline"', system_prompt)
        self.assertIn("each string must be at most 160 characters", system_prompt)
        self.assertIn("never repeat a word or phrase", system_prompt)

    def test_first_json_object_ignores_trailing_model_output(self) -> None:
        self.assertEqual(
            _first_json_object('preface {"action":{"type":"abstain"}} {"extra":true}'),
            {"action": {"type": "abstain"}},
        )

    def test_calibration_restores_identity_assets_and_registered_tool(self) -> None:
        payload = calibrate_planner_payload(
            {
                "request-id": "hallucinated",
                "action": {
                    "type": "tool_call",
                    "tool": "language_guided_points_segmentation",
                    "arguments": {
                        "image_path": "wrong.png",
                        "point_cloud_path": "wrong.txt",
                        "query": "Segment the ditch.",
                        "return_empty_result": True,
                    },
                },
            },
            {
                "request_id": "request:real",
                "assets": {
                    "image_path": "artifact://image",
                    "point_cloud_path": "artifact://points",
                },
            },
            self.registry,
        )
        self.assertEqual(payload["request_id"], "request:real")
        self.assertNotIn("request-id", payload)
        self.assertEqual(payload["action"]["tool"], "language_guided_point_segmentation")
        self.assertEqual(payload["action"]["arguments"]["image_path"], "artifact://image")
        self.assertEqual(payload["action"]["arguments"]["point_cloud_path"], "artifact://points")
        self.assertNotIn("return_empty_result", payload["action"]["arguments"])

    def test_calibration_resolves_descriptive_tool_alias(self) -> None:
        payload = calibrate_planner_payload(
            {
                "action": {
                    "type": "tool_call",
                    "tool": "language_guided_scene_analysis",
                    "arguments": {},
                }
            },
            {"request_id": "request:alias", "assets": {}},
            self.registry,
        )
        self.assertEqual(payload["action"]["tool"], "language_guided_point_segmentation")

    def test_calibration_maps_retired_multimodal_tool_to_point_tool(self) -> None:
        payload = calibrate_planner_payload(
            {
                "action": {
                    "type": "tool_call",
                    "tool": "multimodal_semantic_segmentation",
                    "arguments": {
                        "image_path": "artifact://image",
                        "point_cloud_path": "artifact://points",
                    },
                }
            },
            {
                "request_id": "request:retired-tool",
                "assets": {
                    "image_path": "artifact://image",
                    "point_cloud_path": "artifact://points",
                },
            },
            self.registry,
        )
        self.assertEqual(payload["action"]["tool"], "point_semantic_segmentation")
        self.assertEqual(
            payload["action"]["arguments"],
            {"point_cloud_path": "artifact://points"},
        )

    def test_calibration_assigns_unique_ids_to_workflow_steps(self) -> None:
        payload = calibrate_planner_payload(
            {
                "action": {
                    "type": "workflow",
                    "steps": [
                        {"tool": "image_change_detection", "arguments": {}},
                        {
                            "step_id": "",
                            "tool": "result_quality_verification",
                            "depends_on": ["change"],
                            "arguments": {"input": "${change.artifacts.change_mask}"},
                        },
                        {"step_id": "step_1", "tool": "geometry_relation_analysis", "arguments": {}},
                    ],
                }
            },
            {"request_id": "request:workflow", "assets": {}},
            self.registry,
        )
        self.assertEqual(
            [step["step_id"] for step in payload["action"]["steps"]],
            ["change", "step_2", "step_1"],
        )

    def test_calibration_repairs_producer_from_unique_artifact_contract(self) -> None:
        payload = calibrate_planner_payload(
            {
                "action": {
                    "type": "workflow",
                    "steps": [
                        {
                            "step_id": "segment_scene",
                            "tool": "language_guided_point_segmentation",
                            "arguments": {"query": "识别沟渠和裸地"},
                        },
                        {
                            "step_id": "measure",
                            "tool": "geometry_relation_analysis",
                            "depends_on": ["segment_scene"],
                            "arguments": {
                                "segmentation_result_path": "${segment_scene.artifacts.point_labels}",
                                "operation": "class_statistics",
                                "target_class_id": 14,
                            },
                        },
                    ],
                }
            },
            {
                "request_id": "request:artifact-repair",
                "assets": {
                    "image_path": "artifact://image",
                    "point_cloud_path": "artifact://points",
                },
            },
            self.registry,
        )
        segment, measure = payload["action"]["steps"]
        self.assertEqual(segment["tool"], "point_semantic_segmentation")
        self.assertEqual(segment["arguments"], {"point_cloud_path": "artifact://points"})
        self.assertEqual(measure["arguments"]["segmentation_result_path"], "${segment_scene.artifacts.point_labels}")


if __name__ == "__main__":
    unittest.main()
