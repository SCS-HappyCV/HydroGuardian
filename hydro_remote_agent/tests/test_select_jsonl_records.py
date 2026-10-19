from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydro_remote_agent.tools.select_jsonl_records import main


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def test_selects_in_input_order_from_execution_ids(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    run = tmp_path / "run.jsonl"
    output = tmp_path / "selected.jsonl"
    _write_jsonl(
        gold,
        [
            {"request_id": "a", "action_type": "direct"},
            {"request_id": "b", "action_type": "tool_call"},
            {"request_id": "c", "action_type": "workflow"},
        ],
    )
    _write_jsonl(run, [{"request_id": "c"}, {"request_id": "b"}])

    assert main(["--input", str(gold), "--output", str(output), "--ids-from", str(run)]) == 0
    selected = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [record["request_id"] for record in selected] == ["b", "c"]


def test_expected_count_rejects_incomplete_selection(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    output = tmp_path / "selected.jsonl"
    _write_jsonl(gold, [{"request_id": "a", "action_type": "direct"}])

    with pytest.raises(ValueError, match="Expected 2 records"):
        main(["--input", str(gold), "--output", str(output), "--expected-count", "2"])


def test_rejects_duplicate_execution_ids(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    run = tmp_path / "run.jsonl"
    output = tmp_path / "selected.jsonl"
    _write_jsonl(gold, [{"request_id": "a", "action_type": "tool_call"}])
    _write_jsonl(run, [{"request_id": "a"}, {"request_id": "a"}])

    with pytest.raises(ValueError, match="Duplicate requested ID"):
        main(["--input", str(gold), "--output", str(output), "--ids-from", str(run)])


def test_selects_action_type_from_frozen_assistant_message(tmp_path: Path) -> None:
    gold = tmp_path / "gold.jsonl"
    output = tmp_path / "selected.jsonl"
    _write_jsonl(
        gold,
        [
            {
                "id": "dense",
                "messages": [
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "schema_version": "1.0",
                                "request_id": "dense",
                                "intent": "semantic_segmentation",
                                "action": {"type": "tool_call", "tool": "point_semantic_segmentation", "arguments": {}},
                                "expected_output": {"type": "point_labels", "coordinate_space": "point_cloud"},
                            }
                        ),
                    }
                ],
            }
        ],
    )

    assert main(
        ["--input", str(gold), "--output", str(output), "--action-type", "tool_call", "--expected-count", "1"]
    ) == 0
