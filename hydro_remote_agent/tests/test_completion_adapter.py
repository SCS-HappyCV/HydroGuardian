from __future__ import annotations

import json
from pathlib import Path

from hydro_remote_agent.rewards.completion_adapter import adapt_completion
from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


ROOT = Path(__file__).resolve().parents[2]


def request() -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "diag:adapter:v1",
        "intent": "class_segmentation",
        "action": {"type": "tool_call", "tool": "multimodal_semantic_segmentation", "arguments": {"image_path": "/tmp/image.png", "point_cloud_path": "/tmp/points.txt", "return_probabilities": True, "target_class_ids": [9]}, "verification": "required"},
        "expected_output": {"coordinate_space": "source_point_cloud", "type": "point_mask"},
    }


def test_all_legal_wrappers_score_identically() -> None:
    gold = request()
    payload = json.dumps(gold, ensure_ascii=False)
    wrappers = [payload, gold, [{"role": "assistant", "content": payload}], [{"content": payload}], [{"role": "user", "content": "please answer"}, {"role": "assistant", "content": payload}]]
    engine = GoldActionReward(load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml"))
    for wrapped in wrappers:
        result = adapt_completion(wrapped)
        assert result.valid, result.error
        assert engine.score(result.payload, gold).total == 1.0


def test_invalid_and_repeated_wrappers_are_explicitly_invalid() -> None:
    gold = request()
    payload = json.dumps(gold, ensure_ascii=False)
    bad_values = ["{not-json", [ {"role": "assistant", "content": payload}, {"role": "assistant", "content": payload}], {"content": {"role": "assistant", "content": payload}}, {"content": "not-json"}]
    for bad in bad_values:
        result = adapt_completion(bad)
        assert not result.valid
        assert result.error
