from __future__ import annotations

import unittest

from hydro_remote_agent.runtime.contracts import ExpertResult
from hydro_remote_agent.workflow.contracts import WorkflowResult, WorkflowStepResult
from hydro_remote_agent.workflow.risk_rules import compile_risk_candidates


def _result(
    tool: str,
    metrics: dict,
    arguments: dict | None = None,
    artifacts: dict | None = None,
) -> ExpertResult:
    return ExpertResult(
        schema_version="1.0",
        invocation_id=f"{tool}-result",
        tool=tool,
        tool_version="1.0",
        backend="test",
        status="succeeded",
        started_at="2026-08-09T00:00:00+00:00",
        finished_at="2026-08-09T00:00:01+00:00",
        duration_ms=1.0,
        coordinate_space="none",
        result_types=(),
        artifacts=artifacts or {},
        manifest_path="manifest.json",
        arguments=arguments or {},
        metrics=metrics,
    )


def _quality(verdict: str = "passed", score: float = 1.0, abstention: bool = False) -> ExpertResult:
    return _result(
        "result_quality_verification",
        {
            "verdict": verdict,
            "quality_score": score,
            "abstention_recommended": abstention,
        },
        artifacts={"quality_report": "artifact://quality", "diagnostic_overlay": "artifact://overlay"},
    )


def _workflow(step: WorkflowStepResult) -> WorkflowResult:
    return WorkflowResult(
        schema_version="1.0",
        execution_id="risk-test",
        request_id="request-risk-test",
        intent="inspection",
        status="succeeded",
        started_at="2026-08-09T00:00:00+00:00",
        finished_at="2026-08-09T00:00:01+00:00",
        duration_ms=1.0,
        steps=(step,),
        terminal_artifacts={},
        manifest_path="workflow.json",
    )


class RiskRulesTest(unittest.TestCase):
    def test_change_regions_create_traceable_candidate(self) -> None:
        step = WorkflowStepResult(
            step_id="change",
            tool="image_change_detection",
            status="succeeded",
            resolved_arguments={},
            result=_result(
                "image_change_detection",
                {"changed_pixels": 320, "changed_ratio": 0.0125, "region_count": 3},
                artifacts={"change_regions": "artifact://regions", "change_mask": "artifact://mask"},
            ),
            verification_result=_quality(),
        )
        candidates = compile_risk_candidates(_workflow(step))
        self.assertEqual(len(candidates), 1)
        payload = candidates[0].to_dict()
        self.assertEqual(payload["risk_type"], "change_anomaly_candidate")
        self.assertEqual(payload["region_scope"]["kind"], "artifact_regions")
        self.assertTrue(payload["quality_gate"]["automation_allowed"])
        self.assertIn("artifact://regions", payload["evidence_refs"])
        self.assertTrue(payload["review_required"])

    def test_empty_change_result_does_not_create_candidate(self) -> None:
        step = WorkflowStepResult(
            step_id="change",
            tool="image_change_detection",
            status="succeeded",
            resolved_arguments={},
            result=_result(
                "image_change_detection",
                {"changed_pixels": 0, "changed_ratio": 0.0, "region_count": 0},
            ),
            verification_result=_quality(),
        )
        self.assertEqual(compile_risk_candidates(_workflow(step)), ())

    def test_statistics_and_no_target_results_do_not_become_risks(self) -> None:
        step = WorkflowStepResult(
            step_id="geometry",
            tool="geometry_relation_analysis",
            status="succeeded",
            resolved_arguments={},
            result=_result(
                "geometry_relation_analysis",
                {"outcome": "result", "selected_points": 100, "selected_target_ratio": 1.0},
                arguments={"operation": "class_statistics", "target_class_id": 1},
            ),
            verification_result=_quality(),
        )
        self.assertEqual(compile_risk_candidates(_workflow(step)), ())

    def test_quality_gate_forces_manual_review(self) -> None:
        step = WorkflowStepResult(
            step_id="geometry",
            tool="geometry_relation_analysis",
            status="succeeded",
            resolved_arguments={},
            result=_result(
                "geometry_relation_analysis",
                {"outcome": "result", "selected_points": 20, "selected_target_ratio": 0.4},
                arguments={"operation": "near", "target_class_id": 4, "reference_class_id": 13},
                artifacts={"relation_mask": "artifact://relation"},
            ),
            verification_result=_quality("warning", 0.7, True),
        )
        candidate = compile_risk_candidates(_workflow(step))[0].to_dict()
        self.assertEqual(candidate["risk_level"], "review_required")
        self.assertFalse(candidate["quality_gate"]["automation_allowed"])
        self.assertIn("quality_abstention_recommended", candidate["quality_gate"]["reasons"])


if __name__ == "__main__":
    unittest.main()
