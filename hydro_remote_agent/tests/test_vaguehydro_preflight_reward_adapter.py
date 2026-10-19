from __future__ import annotations

import json
from pathlib import Path

from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.train_vaguehydro_r_m2_grpo_smoke import completion_text


ROOT = Path(__file__).resolve().parents[2]


def _request() -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "diag:adapter",
        "intent": "class_segmentation",
        "action": {
            "type": "tool_call",
            "tool": "multimodal_semantic_segmentation",
            "arguments": {
                "image_path": "/tmp/image.png",
                "point_cloud_path": "/tmp/points.txt",
                "return_probabilities": True,
                "target_class_ids": [9],
            },
            "verification": "required",
        },
        "expected_output": {"coordinate_space": "source_point_cloud", "type": "point_mask"},
    }


def test_structured_trl_completion_is_unwrapped_before_reward() -> None:
    registry = load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml")
    engine = GoldActionReward(registry)
    gold = _request()
    payload = json.dumps(gold, ensure_ascii=False)
    structured = [{"role": "assistant", "content": payload}]
    assert engine.score(payload, gold).total == 1.0
    assert engine.score(structured, gold).invalid
    assert engine.score(completion_text(structured), gold).total == 1.0
