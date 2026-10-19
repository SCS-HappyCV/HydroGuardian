from __future__ import annotations

import copy
import json
from pathlib import Path

from hydro_remote_agent.runtime import build_mock_runtime
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.replay_frozen_agent_condition import replay_record
from hydro_remote_agent.workflow import AgentExecutor


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _request(request_id: str, tool: str = "multimodal_semantic_segmentation") -> dict:
    arguments = {
        "image_path": "image.png",
        "point_cloud_path": "points.txt",
        "return_probabilities": True,
    }
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "intent": "semantic_segmentation",
        "action": {"type": "tool_call", "tool": tool, "arguments": arguments},
        "expected_output": {"type": "point_labels", "coordinate_space": "source_point_cloud"},
    }


def test_preserves_rows_that_do_not_use_replacement_tool(tmp_path: Path) -> None:
    registry = load_tool_registry(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
    runtime = build_mock_runtime(registry, tmp_path / "experts")
    executor = AgentExecutor(runtime, tmp_path / "executions")
    source = {
        "id": "direct-01",
        "condition": "source",
        "prediction": json.dumps(
            {
                "schema_version": "1.0",
                "request_id": "direct-01",
                "intent": "attribute_judgement",
                "action": {"type": "direct_answer", "answer": "Yes."},
                "expected_output": {"type": "text", "coordinate_space": "none"},
            }
        ),
        "execution": {"id": "direct-01", "status": "succeeded"},
    }
    try:
        row, mode = replay_record(
            source,
            "replacement",
            executor,
            registry,
            {"multimodal_semantic_segmentation"},
            {"multimodal_semantic_segmentation": "point_semantic_segmentation"},
            {},
        )
    finally:
        runtime.shutdown()

    assert mode == "preserved"
    assert row["execution"] == source["execution"]
    assert row["replacement_replay"]["reason"] == "replacement_tool_not_used"


def test_reuses_identical_aliased_execution_without_invoking_runtime(tmp_path: Path) -> None:
    registry = load_tool_registry(PACKAGE_ROOT / "configs" / "tool_registry.yaml")
    runtime = build_mock_runtime(registry, tmp_path / "experts")
    executor = AgentExecutor(runtime, tmp_path / "executions")
    source = {
        "id": "dense-01",
        "condition": "source",
        "prediction": json.dumps(_request("dense-01")),
        "execution": {"id": "dense-01", "status": "failed"},
    }
    executed_request = copy.deepcopy(_request("dense-01"))
    executed_request["action"]["tool"] = "point_semantic_segmentation"
    executed_request["action"]["arguments"] = {
        "point_cloud_path": "points.txt",
        "return_probabilities": True,
    }
    cached_execution = {"id": "dense-01", "status": "succeeded", "result": {"status": "succeeded"}}
    cache = {
        json.dumps(executed_request, ensure_ascii=False, separators=(",", ":"), sort_keys=True): {
            "execution": cached_execution,
            "source_path": "oracle.jsonl",
            "source_id": "dense-01",
        }
    }
    try:
        row, mode = replay_record(
            source,
            "replacement",
            executor,
            registry,
            {"multimodal_semantic_segmentation"},
            {"multimodal_semantic_segmentation": "point_semantic_segmentation"},
            cache,
        )
    finally:
        runtime.shutdown()

    assert mode == "reused"
    assert row["execution"] == cached_execution
    assert row["executed_request"] == executed_request
    assert row["replacement_replay"]["reuse_source_path"] == "oracle.jsonl"
