from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Optional

from hydro_remote_agent.cmge_planner import CMGE_PLAN_SCHEMA_VERSION, cmge_assistant_target
from hydro_remote_agent.evaluation.routing import iter_jsonl, parse_json_response
from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


def _rows(path: Path) -> list[dict[str, Any]]:
    return [row for _, row in iter_jsonl(path)]


def _target(row: Mapping[str, Any]) -> dict[str, Any]:
    return cmge_assistant_target(row)


def _prediction(row: Mapping[str, Any]) -> Any:
    for key in ("prediction", "output", "response"):
        if key in row:
            return row[key]
    return row.get("plan")


def _score_plan(
    gold: Mapping[str, Any],
    raw_prediction: Any,
    registry,
) -> dict[str, Any]:
    result = {
        "parse_valid": False,
        "schema_valid": False,
        "compound_id_correct": False,
        "claim_count_correct": False,
        "claim_route_accuracy": 0.0,
        "claim_intent_accuracy": 0.0,
        "claim_role_accuracy": 0.0,
        "claim_component_accuracy": 0.0,
        "claim_request_valid_rate": 0.0,
        "claim_request_exact_rate": 0.0,
        "plan_exact": False,
        "complete": False,
        "correct": False,
    }
    try:
        prediction = parse_json_response(raw_prediction)
    except Exception:
        return result
    result["parse_valid"] = True
    result["compound_id_correct"] = prediction.get("compound_id") == gold.get("compound_id")
    claims = prediction.get("claims")
    gold_claims = gold.get("claims")
    if not isinstance(claims, list) or not isinstance(gold_claims, list):
        return result
    result["claim_count_correct"] = len(claims) == len(gold_claims) == 2
    merge = prediction.get("merge")
    result["schema_valid"] = bool(
        prediction.get("schema_version") == CMGE_PLAN_SCHEMA_VERSION
        and result["claim_count_correct"]
        and all(isinstance(claim, Mapping) for claim in claims)
        and isinstance(merge, Mapping)
        and merge.get("type") == "claimwise_union"
        and merge.get("required_claim_indices") == [0, 1]
    )
    candidates_by_index = {
        claim.get("claim_index"): claim
        for claim in claims
        if isinstance(claim, Mapping) and claim.get("claim_index") in (0, 1)
    }
    route_correct = 0
    intent_correct = 0
    role_correct = 0
    component_correct = 0
    request_valid = 0
    request_exact = 0
    for index, gold_claim in enumerate(gold_claims):
        candidate = candidates_by_index.get(index, {})
        route_correct += int(candidate.get("route") == gold_claim.get("route"))
        intent_correct += int(candidate.get("intent") == gold_claim.get("intent"))
        role_correct += int(candidate.get("role") == gold_claim.get("role"))
        request = candidate.get("request")
        gold_request = gold_claim.get("request")
        component_correct += int(_component_signature(request) == _component_signature(gold_request))
        request_exact += int(request == gold_request)
        if isinstance(request, Mapping):
            try:
                AgentRequest.from_dict(request, registry)
                request_valid += 1
            except Exception:
                pass
    result["claim_route_accuracy"] = route_correct / 2
    result["claim_intent_accuracy"] = intent_correct / 2
    result["claim_role_accuracy"] = role_correct / 2
    result["claim_component_accuracy"] = component_correct / 2
    result["claim_request_valid_rate"] = request_valid / 2
    result["claim_request_exact_rate"] = request_exact / 2
    result["plan_exact"] = prediction == gold
    result["complete"] = bool(
        result["schema_valid"]
        and result["compound_id_correct"]
        and result["claim_count_correct"]
        and result["claim_route_accuracy"] == 1.0
        and result["claim_request_valid_rate"] == 1.0
    )
    result["correct"] = bool(
        result["complete"]
        and result["claim_intent_accuracy"] == 1.0
        and result["claim_role_accuracy"] == 1.0
        and result["claim_component_accuracy"] == 1.0
    )
    return result


def _component_signature(request: Any) -> Any:
    if not isinstance(request, Mapping):
        return None
    action = request.get("action")
    if not isinstance(action, Mapping):
        return None
    action_type = action.get("type")
    if action_type == "direct_answer":
        return ("direct_answer",)
    if action_type == "tool_call":
        return ("tool_call", action.get("tool"))
    if action_type == "workflow":
        steps = action.get("steps")
        if not isinstance(steps, list):
            return ("workflow", None)
        return (
            "workflow",
            tuple(
                step.get("tool") if isinstance(step, Mapping) else None
                for step in steps
            ),
        )
    return (action_type,)


def evaluate(gold_path: Path, prediction_path: Path, registry_path: Path) -> dict[str, Any]:
    gold_rows = _rows(gold_path)
    prediction_rows = {
        str(row.get("id") or row.get("compound_id")): row
        for row in _rows(prediction_path)
    }
    registry = load_tool_registry(registry_path)
    scored = []
    for gold_row in gold_rows:
        record_id = str(gold_row.get("id") or gold_row.get("compound_id"))
        score = _score_plan(_target(gold_row), _prediction(prediction_rows.get(record_id, {})), registry)
        scored.append({"id": record_id, **score})
    count = len(scored)
    intent_confusion: Counter[str] = Counter()
    component_confusion: Counter[str] = Counter()
    for gold_row in gold_rows:
        record_id = str(gold_row.get("id") or gold_row.get("compound_id"))
        gold = _target(gold_row)
        raw_prediction = _prediction(prediction_rows.get(record_id, {}))
        try:
            prediction = parse_json_response(raw_prediction)
        except Exception:
            continue
        claims = prediction.get("claims")
        if not isinstance(claims, list):
            continue
        candidates = {
            claim.get("claim_index"): claim
            for claim in claims
            if isinstance(claim, Mapping)
        }
        for index, gold_claim in enumerate(gold.get("claims", [])):
            candidate = candidates.get(index, {})
            intent_confusion[
                f"{gold_claim.get('intent')} -> {candidate.get('intent', '<missing>')}"
            ] += 1
            component_confusion[
                f"{_component_signature(gold_claim.get('request'))} -> "
                f"{_component_signature(candidate.get('request'))}"
            ] += 1
    report = {
        "schema_version": "cmge.planner_eval.v1",
        "gold_count": count,
        "prediction_count": len(prediction_rows),
        "parse_rate": sum(row["parse_valid"] for row in scored) / count if count else None,
        "schema_valid_rate": sum(row["schema_valid"] for row in scored) / count if count else None,
        "compound_id_accuracy": sum(row["compound_id_correct"] for row in scored) / count if count else None,
        "claim_route_accuracy": sum(row["claim_route_accuracy"] for row in scored) / count if count else None,
        "claim_intent_accuracy": sum(row["claim_intent_accuracy"] for row in scored) / count if count else None,
        "claim_role_accuracy": sum(row["claim_role_accuracy"] for row in scored) / count if count else None,
        "claim_component_accuracy": sum(row["claim_component_accuracy"] for row in scored) / count if count else None,
        "claim_request_valid_rate": sum(row["claim_request_valid_rate"] for row in scored) / count if count else None,
        "claim_request_exact_rate": sum(row["claim_request_exact_rate"] for row in scored) / count if count else None,
        "plan_exact_rate": sum(row["plan_exact"] for row in scored) / count if count else None,
        "complete_plan_rate": sum(row["complete"] for row in scored) / count if count else None,
        "correct_plan_rate": sum(row["correct"] for row in scored) / count if count else None,
        "failure_counts": dict(
            Counter(
                "parse_invalid" if not row["parse_valid"] else
                "schema_invalid" if not row["schema_valid"] else
                "incomplete"
                for row in scored
                if not row["complete"]
            )
        ),
        "intent_confusion": dict(sorted(intent_confusion.items())),
        "component_confusion": dict(sorted(component_confusion.items())),
    }
    return {"report": report, "rows": scored}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate CMGE planner outputs.")
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--gold-as-predictions", action="store_true")
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.gold_as_predictions:
        gold_rows = _rows(args.gold)
        prediction_path = args.output.with_suffix(".gold_predictions.jsonl")
        prediction_path.parent.mkdir(parents=True, exist_ok=True)
        prediction_path.write_text(
            "".join(
                json.dumps(
                    {
                        "id": str(row.get("id") or row.get("compound_id")),
                        "prediction": _target(row),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
                for row in gold_rows
            ),
            encoding="utf-8",
        )
    elif args.predictions is not None:
        prediction_path = args.predictions
    else:
        raise ValueError("--predictions is required unless --gold-as-predictions is set")
    result = evaluate(args.gold, prediction_path, args.registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["report"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
