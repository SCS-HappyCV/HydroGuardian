import json
from pathlib import Path

import pytest

from hydro_remote_agent.tools.merge_routing_predictions import merge_predictions


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_merge_predictions_restores_manifest_order(tmp_path: Path) -> None:
    manifest = tmp_path / "gold.jsonl"
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    output = tmp_path / "merged.jsonl"
    _write(manifest, [{"id": "a"}, {"id": "b"}, {"id": "c"}])
    _write(first, [{"id": "c", "prediction": 3}, {"id": "a", "prediction": 1}])
    _write(second, [{"id": "b", "prediction": 2}])
    assert merge_predictions(manifest, [first, second], output) == 3
    assert [json.loads(line)["id"] for line in output.read_text().splitlines()] == ["a", "b", "c"]


def test_merge_predictions_rejects_duplicates(tmp_path: Path) -> None:
    manifest = tmp_path / "gold.jsonl"
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    _write(manifest, [{"id": "a"}])
    _write(first, [{"id": "a"}])
    _write(second, [{"id": "a"}])
    with pytest.raises(ValueError, match="duplicate"):
        merge_predictions(manifest, [first, second], tmp_path / "merged.jsonl")
