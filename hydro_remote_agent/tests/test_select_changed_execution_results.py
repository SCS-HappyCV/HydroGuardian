import json

from hydro_remote_agent.tools.select_changed_execution_results import select_results


def _write(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_selects_capability_policy_subset(tmp_path):
    predictions = tmp_path / "predictions.jsonl"
    results = tmp_path / "results.jsonl"
    output = tmp_path / "selected.jsonl"
    _write(predictions, [
        {"id": "a", "prediction": {}, "capability_policy": {"changed": True}},
        {"id": "b", "prediction": {}, "capability_policy": {"changed": False}},
    ])
    _write(results, [{"id": "a"}, {"id": "b"}, {"id": "c"}])
    report = select_results(predictions, results, output)
    assert report["selected_count"] == 1
    assert json.loads(output.read_text(encoding="utf-8"))["id"] == "a"
