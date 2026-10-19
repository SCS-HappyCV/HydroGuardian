from __future__ import annotations

import json
from pathlib import Path

from hydro_remote_agent.tools.merge_recorded_agent_e2e_run import merge_recorded_run


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_merge_recorded_run_preserves_prediction_and_execution(tmp_path: Path) -> None:
    request_id = "q:00-000001-attribute-3-1:direct:en:l0"
    request = {
        "schema_version": "1.0",
        "request_id": request_id,
        "intent": "attribute_judgement",
        "action": {"type": "direct_answer", "answer": "Yes."},
        "expected_output": {"type": "text", "coordinate_space": "none"},
    }
    gold = tmp_path / "gold.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    executions = tmp_path / "executions.jsonl"
    output = tmp_path / "run.jsonl"
    _write_jsonl(gold, [{"id": request_id, "gold_request": request}])
    _write_jsonl(
        predictions,
        [{
            "id": request_id,
            "prediction": json.dumps(request),
            "inference": {
                "batch_seconds": 2.0,
                "batch_size": 2,
                "generated_tokens": 12,
            },
        }],
    )
    _write_jsonl(
        executions,
        [{
            "id": request_id,
            "status": "succeeded",
            "result": {
                "status": "succeeded",
                "duration_ms": 5.0,
                "execution_mode": "planner_only",
            },
        }],
    )

    manifest = merge_recorded_run(
        gold,
        predictions,
        executions,
        output,
        "vaguehydro_lora",
    )
    row = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["request_count"] == 1
    assert row["prediction"] == json.dumps(request)
    assert row["execution"]["status"] == "succeeded"
    assert row["timing"]["planner_ms"] == 1000.0
    assert row["timing"]["execution_ms"] == 5.0
    assert row["provenance"]["execution_replayed"] is False
