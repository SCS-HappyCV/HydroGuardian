import json
from pathlib import Path

from hydro_remote_agent.baselines.rule_router import RuleRouter
from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import ToolRegistry, load_tool_registry


ROOT = Path(__file__).resolve().parents[2]


def _record(query: str) -> dict:
    return {
        "id": "ignored:gold-looking-id",
        "metadata": {"canonical_intent": "must_not_be_read"},
        "messages": [{
            "role": "user",
            "content": json.dumps({
                "request_id": "rule:test", "query": query,
                "assets": {"image_path": "tile.png", "point_cloud_path": "tile.txt"},
            }),
        }],
    }


def _registry() -> ToolRegistry:
    return load_tool_registry(ROOT / "hydro_remote_agent" / "configs" / "tool_registry.yaml")


def test_rule_router_builds_relation_workflow_without_gold_fields() -> None:
    result = RuleRouter().plan(_record("Segment all Dirtroad points that are near Woodland."))
    request = AgentRequest.from_dict(result.request, _registry())
    assert request.intent == "relation_segmentation"
    assert request.action.type == "workflow"
    assert result.trace["detected_class_ids"] == [4, 11]
    assert result.trace["input_fields"] == [
        "messages.user.content.query", "messages.user.content.assets",
    ]


def test_rule_router_uses_language_tool_for_no_target_request() -> None:
    result = RuleRouter().plan(_record("Extract all Shed points and return an empty result if none exist."))
    request = AgentRequest.from_dict(result.request, _registry())
    assert request.intent == "class_segmentation"
    assert request.action.type == "tool_call"
    assert request.action.tool == "language_guided_point_segmentation"


def test_rule_router_builds_direct_presence_answer() -> None:
    result = RuleRouter().plan(_record("Is Grassland present in this scene?"))
    request = AgentRequest.from_dict(result.request, _registry())
    assert request.intent == "class_presence"
    assert request.action.type == "direct_answer"
