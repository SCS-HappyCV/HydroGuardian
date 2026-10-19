from pathlib import Path

from hydro_remote_agent.capability_policy import apply_capability_policy, load_capability_policy
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = load_tool_registry(ROOT / "hydro_remote_agent/configs/tool_registry.yaml")
POLICY = load_capability_policy(
    ROOT / "hydro_remote_agent/configs/cmge_capability_policy.attribute_ptv3.yaml",
    REGISTRY,
)


def test_policy_rewrites_matching_attribute_call_and_filters_arguments():
    request = {
        "schema_version": "1.0",
        "request_id": "a",
        "intent": "attribute_segmentation",
        "action": {
            "type": "tool_call",
            "tool": "language_guided_point_segmentation",
            "arguments": {
                "point_cloud_path": "tile.txt",
                "image_path": "tile.png",
                "query": "broad bareland",
                "target_class_ids": [12],
            },
        },
        "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
    }

    rewritten, decisions = apply_capability_policy(request, POLICY, REGISTRY)

    assert rewritten["action"]["tool"] == "point_semantic_segmentation"
    assert rewritten["action"]["arguments"] == {
        "point_cloud_path": "tile.txt",
        "target_class_ids": [12],
    }
    assert decisions[0]["rule_id"] == "language_call_to_ptv3"


def test_policy_preserves_nonmatching_source_tool():
    request = {
        "intent": "attribute_segmentation",
        "action": {
            "type": "tool_call",
            "tool": "multimodal_semantic_segmentation",
            "arguments": {"point_cloud_path": "tile.txt", "image_path": "tile.png"},
        },
    }

    rewritten, decisions = apply_capability_policy(request, POLICY, REGISTRY)

    assert rewritten == request
    assert decisions == []
