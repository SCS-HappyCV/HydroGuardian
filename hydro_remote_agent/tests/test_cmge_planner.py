import json
from pathlib import Path

from hydro_remote_agent.cmge_planner import (
    CMGE_PLAN_SCHEMA_VERSION,
    build_plan_target,
    cmge_planner_messages,
)
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.build_cmge_conditions import read_jsonl
from hydro_remote_agent.tools.build_cmge_sft import build_record
from hydro_remote_agent.tools.evaluate_cmge_planner import _score_plan


ROOT = Path(__file__).parents[1]
COMPOUND_PATH = ROOT.parent / "runs" / "cmge_pilot_v1" / "smoke20_server_paths" / "compound_manifest.jsonl"
REGISTRY_PATH = ROOT / "configs" / "tool_registry.yaml"


def test_build_plan_target_has_two_valid_component_requests():
    compound = read_jsonl(COMPOUND_PATH)[0]
    registry = load_tool_registry(REGISTRY_PATH)
    target = build_plan_target(compound, "/workspace/HydroGuardian/benchmark/10M")

    assert target["schema_version"] == CMGE_PLAN_SCHEMA_VERSION
    assert [claim["claim_index"] for claim in target["claims"]] == [0, 1]
    assert [claim["route"] for claim in target["claims"]] == ["direct_answer", "tool_call"]
    for claim in target["claims"]:
        from hydro_remote_agent.schemas.agent_action import AgentRequest

        AgentRequest.from_dict(claim["request"], registry)


def test_sft_record_hides_assistant_target_from_planner_messages():
    compound = read_jsonl(COMPOUND_PATH)[0]
    registry = load_tool_registry(REGISTRY_PATH)
    record = build_record(
        compound,
        registry,
        "/workspace/HydroGuardian/benchmark/10M",
    )
    messages = cmge_planner_messages(record)
    assert [message["role"] for message in messages] == ["system", "user"]
    assert json.dumps(messages, ensure_ascii=False).find('"claims"') == -1
    user_payload = json.loads(record["messages"][1]["content"])
    assert user_payload["query"]
    assert "Also," in user_payload["query"]


def test_gold_plan_scores_complete():
    compound = read_jsonl(COMPOUND_PATH)[0]
    registry = load_tool_registry(REGISTRY_PATH)
    gold = build_plan_target(
        compound,
        "/workspace/HydroGuardian/benchmark/10M",
    )
    score = _score_plan(gold, gold, registry)
    assert score["complete"]
    assert score["correct"]
    assert score["claim_route_accuracy"] == 1.0
    assert score["claim_component_accuracy"] == 1.0
    assert score["claim_request_exact_rate"] == 1.0


def test_partial_plan_metrics_do_not_depend_on_compound_id():
    compound = read_jsonl(COMPOUND_PATH)[0]
    registry = load_tool_registry(REGISTRY_PATH)
    gold = build_plan_target(
        compound,
        "/workspace/HydroGuardian/benchmark/10M",
    )
    prediction = json.loads(json.dumps(gold))
    prediction.pop("compound_id")
    prediction["claims"][0]["route"] = "tool_call"
    prediction["claims"][0]["request"] = {"component": "AgentRequest"}

    score = _score_plan(gold, prediction, registry)

    assert score["schema_valid"]
    assert not score["compound_id_correct"]
    assert score["claim_route_accuracy"] == 0.5
    assert score["claim_request_valid_rate"] == 0.5
    assert not score["complete"]
    assert not score["correct"]
