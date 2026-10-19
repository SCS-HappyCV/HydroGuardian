"""Standalone diagnosis for the v5 all-zero GoldActionReward signal."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.rewards.request_canonicalizer import canonicalize_agent_request
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
def completion_text(completion: Any) -> str:
    if isinstance(completion, str):
        return completion
    if isinstance(completion, list) and completion:
        message = completion[-1]
        if isinstance(message, Mapping) and isinstance(message.get("content", ""), str):
            return message["content"]
    return json.dumps(completion, ensure_ascii=False)


def gold_action(record: Mapping[str, Any]) -> dict[str, Any]:
    for message in reversed(record["messages"]):
        if message.get("role") == "assistant":
            value = json.loads(message["content"])
            if isinstance(value, dict):
                return value
    raise ValueError(f"Record {record.get('id')} has no assistant gold action")

COMPONENTS = ("schema", "action", "tool", "argument", "workflow", "stop")


def sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def load_record(path: Path, sample_id: str) -> dict[str, Any]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if str(row.get("id")) == sample_id:
                return row
    raise KeyError(sample_id)


def jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def diff_paths(gold: Any, pred: Any, path: str = "$") -> list[dict[str, Any]]:
    if isinstance(gold, Mapping) and isinstance(pred, Mapping):
        out = []
        for key in sorted(set(gold) | set(pred), key=str):
            out.extend(diff_paths(gold.get(key), pred.get(key), f"{path}.{key}"))
        return out
    if isinstance(gold, list) and isinstance(pred, list):
        if gold == pred:
            return []
        return [{"path": path, "gold": gold, "pred": pred, "reason": "list_mismatch"}]
    if gold != pred:
        return [{"path": path, "gold": gold, "pred": pred, "reason": "value_mismatch"}]
    return []


def field_replace_variants(gold: dict[str, Any], pred: dict[str, Any]) -> dict[str, dict[str, Any]]:
    variants: dict[str, dict[str, Any]] = {"gold_exact": copy.deepcopy(gold)}
    for field in ("schema_version", "request_id", "intent", "expected_output"):
        candidate = copy.deepcopy(gold)
        if field in pred:
            candidate[field] = copy.deepcopy(pred[field])
        variants[f"replace_{field}"] = candidate
    gold_action_payload = gold.get("action", {})
    pred_action_payload = pred.get("action", {})
    for field in ("type", "tool", "arguments", "verification", "steps", "answer", "question", "missing_fields", "reason", "error_code", "recoverable"):
        candidate = copy.deepcopy(gold)
        if field in pred_action_payload:
            candidate.setdefault("action", {})[field] = copy.deepcopy(pred_action_payload[field])
        variants[f"replace_action_{field}"] = candidate
    return variants


def minimal_mutation_variants(gold: dict[str, Any]) -> dict[str, dict[str, Any]]:
    variants = {}
    candidate = copy.deepcopy(gold)
    candidate["schema_version"] = "9.9"
    variants["mutate_schema_version"] = candidate
    candidate = copy.deepcopy(gold)
    candidate["action"]["type"] = "direct_answer"
    candidate["action"].pop("tool", None)
    candidate["action"].pop("arguments", None)
    candidate["action"]["answer"] = "wrong action"
    variants["mutate_action_type"] = candidate
    candidate = copy.deepcopy(gold)
    candidate["action"]["tool"] = "point_semantic_segmentation"
    variants["mutate_tool"] = candidate
    candidate = copy.deepcopy(gold)
    candidate["action"]["arguments"]["target_class_ids"] = [8]
    variants["mutate_argument"] = candidate
    candidate = copy.deepcopy(gold)
    candidate["action"]["verification"] = "auto"
    variants["mutate_workflow_or_policy"] = candidate
    candidate = copy.deepcopy(gold)
    candidate["request_id"] = "different-request"
    variants["mutate_stop_or_non_scoring_metadata"] = candidate
    return variants


def score(engine: GoldActionReward, candidate: Any, gold: dict[str, Any]) -> dict[str, Any]:
    result = engine.score(candidate, gold)
    return result.to_dict()


def run(root: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    v5 = root / "runs/hydro_remote_agent/vaguehydro_grpo_gold_action_formal_v5_preflight"
    cfg = json.loads((v5 / "PREFLIGHT_ONLY_CONFIG.json").read_text(encoding="utf-8"))
    report = json.loads((v5 / "seed_20261011/REAL_TASK_PREFLIGHT_REPORT.json").read_text(encoding="utf-8"))
    sample_id = cfg["data"]["train_sample_ids"][0]
    record = load_record(root / cfg["data"]["train"], sample_id)
    gold = gold_action(record)
    registry = load_tool_registry(root / "hydro_remote_agent/configs/tool_registry.yaml")
    engine = GoldActionReward(registry, cfg["reward"]["weights"])
    raw_candidates = list(report["raw_candidates"])
    parsed_candidates = [json.loads(text) for text in raw_candidates]
    canonical_gold = canonicalize_agent_request(gold, registry)
    canonical_candidates = [canonicalize_agent_request(candidate, registry) for candidate in parsed_candidates]

    details = []
    for index, (raw, candidate, canonical) in enumerate(zip(raw_candidates, parsed_candidates, canonical_candidates)):
        structured_completion = [{"role": "assistant", "content": raw}]
        details.append({
            "index": index,
            "raw_sha256": sha(raw),
            "raw_length": len(raw),
            "parsed_request": candidate,
            "canonical_prediction": canonical.to_dict(),
            "field_differences": diff_paths(gold, candidate),
            "score_raw_string": score(engine, raw, gold),
            "score_structured_message_list": score(engine, structured_completion, gold),
            "score_completion_text_adapter": score(engine, completion_text(structured_completion), gold),
        })

    truth_table = []
    truth_cases = [("gold_exact", gold)] + [(f"candidate_{i}", c) for i, c in enumerate(parsed_candidates)]
    for name, candidate in truth_cases:
        truth_table.append({"case": name, "candidate_shape": type(candidate).__name__, "score": score(engine, candidate, gold)})
    for name, candidate in field_replace_variants(gold, parsed_candidates[0]).items():
        truth_table.append({"case": name, "candidate_shape": type(candidate).__name__, "score": score(engine, candidate, gold)})
    for name, candidate in minimal_mutation_variants(gold).items():
        truth_table.append({"case": name, "candidate_shape": type(candidate).__name__, "score": score(engine, candidate, gold)})

    duplication = {
        "candidate_count": len(raw_candidates),
        "unique_raw_count": len(set(raw_candidates)),
        "raw_sha256": [sha(v) for v in raw_candidates],
        "parsed_json_equal": len({json.dumps(v, sort_keys=True, ensure_ascii=False) for v in parsed_candidates}) == 1,
        "lengths": [len(v) for v in raw_candidates],
        "config_sampling": {key: cfg["sampling"].get(key) for key in ("group_size", "temperature", "top_p", "max_new_tokens")},
        "trl_sampling_contract": {"do_sample": "not explicitly set in v5 GRPOConfig; inherited from TRL generation config", "generation_batch_size": cfg["sampling"]["group_size"]},
        "decoder": cfg["decoder"],
        "prompt_hashes": [sha(row["prompt"]) for row in [{"prompt": record["messages"]}]],
        "interpretation": "Exact raw and parsed equality proves the two retained candidates are duplicates; this report cannot attribute the cause to cache versus deterministic decoder without token-level generation instrumentation."
    }
    report_out = {
        "schema_version": "vaguehydro.reward_diagnostic.v1",
        "sample_id": sample_id,
        "frozen_test_read": False,
        "gold_request": gold,
        "canonical_gold": canonical_gold.to_dict(),
        "candidate_details": details,
        "reward_input_contract": {
            "GoldActionReward.accepted": ["JSON string", "mapping/object"],
            "trl_structured_message_list": "invalid without completion_text adapter",
            "completion_text_adapter": "extracts final assistant content string",
        },
        "candidate_duplication": duplication,
    }
    (output / "DIAG_REPORT.json").write_text(json.dumps(report_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "REWARD_TRUTH_TABLE.json").write_text(json.dumps(truth_table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "CANDIDATE_DUPLICATION_REPORT.json").write_text(json.dumps(duplication, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.root.resolve(), args.output if args.output.is_absolute() else args.root / args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
