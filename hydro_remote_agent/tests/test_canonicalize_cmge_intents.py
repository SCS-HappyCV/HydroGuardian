import copy
import json
from pathlib import Path

from hydro_remote_agent.cmge_planner import canonicalize_cmge_plan


ROOT = Path(__file__).parents[1].parent
PREDICTIONS = (
    ROOT
    / "runs"
    / "cmge_planner_v1"
    / "test100_unseen"
    / "robustness"
    / "same_scene_predictions.jsonl"
)


def _plans():
    return [json.loads(json.loads(line)["prediction"]) for line in PREDICTIONS.read_text(encoding="utf-8").splitlines()]


def test_canonical_intents_are_not_changed():
    plan = next(plan for plan in _plans() if all(claim["intent"] in {
        "class_presence", "attribute_judgement", "relation_judgement",
        "class_segmentation", "attribute_segmentation", "relation_segmentation",
    } for claim in plan["claims"]))

    normalized, changes = canonicalize_cmge_plan(plan)

    assert normalized == plan
    assert changes == []


def test_class_specific_segmentation_alias_is_canonicalized_only_in_intent_fields():
    plan = next(plan for plan in _plans() if any(claim["intent"] == "shed_segmentation" for claim in plan["claims"]))
    expected = copy.deepcopy(plan)
    alias = next(claim for claim in expected["claims"] if claim["intent"] == "shed_segmentation")
    alias["intent"] = "class_segmentation"
    alias["request"]["intent"] = "class_segmentation"

    normalized, changes = canonicalize_cmge_plan(plan)

    assert normalized == expected
    assert changes[0]["source_intent"] == "shed_segmentation"
    assert changes[0]["target_intent"] == "class_segmentation"


def test_semantic_judgement_relation_answer_becomes_relation_judgement():
    plan = next(plan for plan in _plans() if any(claim["intent"] == "semantic_judgement" for claim in plan["claims"]))

    normalized, changes = canonicalize_cmge_plan(plan)
    changed = normalized["claims"][changes[0]["claim_index"]]

    assert changed["intent"] == "relation_judgement"
    assert changed["request"]["intent"] == "relation_judgement"
