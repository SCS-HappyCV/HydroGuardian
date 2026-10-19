import json

from hydro_remote_agent.baselines.react_planner import (
    FINAL_OBSERVATION,
    react_draft_messages,
    react_final_messages,
)


def _record() -> dict:
    return {
        "id": "react:test",
        "images": ["tile.png"],
        "tools": [{"type": "function", "function": {
            "name": "demo_tool", "description": "demo",
            "parameters": {"type": "object", "properties": {}},
        }}],
        "messages": [
            {"role": "system", "content": "Plan."},
            {"role": "user", "content": json.dumps({
                "request_id": "react:test", "query": "Inspect the scene.",
                "assets": {"image_path": "tile.png"},
            })},
        ],
    }


def test_react_messages_do_not_read_or_include_gold_target() -> None:
    record = _record()
    record["messages"].append({"role": "assistant", "content": '{"secret":"gold"}'})
    draft = react_draft_messages(record)
    final = react_final_messages(record, '{"candidate":"demo_tool"}')
    assert "secret" not in json.dumps(draft)
    assert final[-2]["role"] == "assistant"
    assert final[-1]["content"][0]["text"] == FINAL_OBSERVATION
    assert "no specialist tool has been executed" in FINAL_OBSERVATION
