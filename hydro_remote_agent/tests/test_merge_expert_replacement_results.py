import json
from pathlib import Path

import pytest

from hydro_remote_agent.tools.merge_expert_replacement_results import (
    merge_expert_replacement_results,
)


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_merge_replaces_exactly_changed_real_rows(tmp_path):
    predictions = tmp_path / "predictions.jsonl"
    base = tmp_path / "base.jsonl"
    replacement = tmp_path / "replacement.jsonl"
    output = tmp_path / "output.jsonl"
    _write(predictions, [
        {"id": "a", "prediction": {"request_id": "a"}, "tool_alias_rewrite": {"changed": False}},
        {"id": "b", "prediction": {"request_id": "b"}, "tool_alias_rewrite": {"changed": True}},
    ])
    _write(base, [{"id": "a", "status": "succeeded"}, {"id": "b", "status": "succeeded"}])
    replacement_row = {
        "id": "b",
        "status": "succeeded",
        "result": {"execution_mode": "expert_runtime", "is_mock": False},
    }
    _write(replacement, [replacement_row])

    report = merge_expert_replacement_results(predictions, base, replacement, output)

    assert report["replacement_count"] == 1
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"id": "a", "status": "succeeded"}, replacement_row]


def test_merge_rejects_incomplete_replacement_set(tmp_path):
    predictions = tmp_path / "predictions.jsonl"
    base = tmp_path / "base.jsonl"
    replacement = tmp_path / "replacement.jsonl"
    _write(predictions, [
        {"id": "a", "prediction": {"request_id": "a"}, "tool_alias_rewrite": {"changed": True}},
    ])
    _write(base, [{"id": "a", "status": "succeeded"}])
    _write(replacement, [])

    with pytest.raises(ValueError, match="exactly match changed"):
        merge_expert_replacement_results(predictions, base, replacement, tmp_path / "out.jsonl")


def test_merge_accepts_capability_policy_marker(tmp_path):
    predictions = tmp_path / "predictions.jsonl"
    base = tmp_path / "base.jsonl"
    replacement = tmp_path / "replacement.jsonl"
    output = tmp_path / "output.jsonl"
    _write(predictions, [
        {"id": "a", "prediction": {"request_id": "a"}, "capability_policy": {"changed": True}},
    ])
    _write(base, [{"id": "a", "status": "succeeded"}])
    _write(replacement, [{
        "id": "a",
        "status": "succeeded",
        "result": {"execution_mode": "expert_runtime", "is_mock": False},
    }])

    report = merge_expert_replacement_results(predictions, base, replacement, output)

    assert report["replaced_ids"] == ["a"]
