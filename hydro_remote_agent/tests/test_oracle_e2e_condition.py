from __future__ import annotations

import json
from pathlib import Path

from hydro_remote_agent.runtime import build_mock_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.run_oracle_e2e_condition import oracle_run_record
from hydro_remote_agent.workflow import AgentExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_oracle_direct_answer_executes_without_planner(tmp_path: Path) -> None:
    registry = load_tool_registry(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
    runtime = build_mock_runtime(registry, tmp_path / "experts")
    executor = AgentExecutor(runtime, tmp_path / "executions")
    gold_request = {
        "schema_version": "1.0",
        "request_id": "oracle-direct-01",
        "intent": "attribute_judgement",
        "action": {"type": "direct_answer", "answer": "Yes."},
        "expected_output": {"type": "text", "coordinate_space": "none"},
    }
    try:
        row = oracle_run_record(
            {"id": "oracle-direct-01", "gold_request": gold_request},
            executor,
            registry,
        )
    finally:
        runtime.shutdown()

    assert json.loads(row["prediction"]) == gold_request
    assert row["condition"] == "oracle_gold_routing"
    assert row["execution"]["status"] == "succeeded"
    assert row["execution"]["result"]["execution_mode"] == "planner_only"
    assert row["timing"]["planner_ms"] == 0.0
    assert row["generated_tokens"] == 0
    assert row["oracle"]["claim_scope"] == "gold_policy_execution_reference"


def test_oracle_executes_retired_tool_through_audited_alias(tmp_path: Path) -> None:
    registry = load_tool_registry(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
    runtime = build_mock_runtime(registry, tmp_path / "experts")
    executor = AgentExecutor(runtime, tmp_path / "executions")
    gold_request = {
        "schema_version": "1.0",
        "request_id": "oracle-alias-01",
        "intent": "semantic_segmentation",
        "action": {
            "type": "tool_call",
            "tool": "multimodal_semantic_segmentation",
            "arguments": {
                "image_path": "image.png",
                "point_cloud_path": "points.txt",
                "target_class_ids": [13],
                "y_flip": False,
                "return_probabilities": True,
            },
        },
        "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
    }
    try:
        row = oracle_run_record(
            {"id": "oracle-alias-01", "gold_request": gold_request},
            executor,
            registry,
            tool_aliases={"multimodal_semantic_segmentation": "point_semantic_segmentation"},
        )
    finally:
        runtime.shutdown()

    assert json.loads(row["prediction"]) == gold_request
    assert row["executed_request"]["action"]["tool"] == "point_semantic_segmentation"
    assert "image_path" not in row["executed_request"]["action"]["arguments"]
    assert row["execution"]["status"] == "skipped"
    assert row["execution"]["result"]["execution_mode"] == "skipped_mock"
    assert row["oracle"]["execution_tool_aliases"] == {
        "multimodal_semantic_segmentation": "point_semantic_segmentation"
    }
