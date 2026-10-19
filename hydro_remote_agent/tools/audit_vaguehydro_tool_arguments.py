from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from hydro_remote_agent.rewards.completion_adapter import adapt_completion
from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import ToolRegistry, load_tool_registry


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def assistant_target(record: Mapping[str, Any]) -> dict[str, Any]:
    for message in reversed(record.get("messages", [])):
        if message.get("role") == "assistant":
            return json.loads(message["content"])
    raise ValueError(f"record {record.get('id')!r} has no assistant target")


def calls(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    action = payload.get("action")
    if not isinstance(action, Mapping):
        return []
    if action.get("type") == "tool_call":
        return [dict(action)]
    if action.get("type") == "workflow" and isinstance(action.get("steps"), list):
        return [dict(step) for step in action["steps"] if isinstance(step, Mapping)]
    return []


def schema_fields(registry: ToolRegistry, tool: str) -> tuple[set[str], set[str]]:
    try:
        schema = registry.get(tool).arguments_schema
    except KeyError:
        return set(), set()
    return set(schema.get("properties", {})), set(schema.get("required", []))


def prompt_mentions_catalog(messages: Iterable[Mapping[str, Any]], registry: ToolRegistry) -> bool:
    text = "\n".join(str(message.get("content", "")) for message in messages)
    return all(tool.name in text for tool in registry.tools)


def audit_label(payload: Mapping[str, Any], registry: ToolRegistry) -> str | None:
    try:
        AgentRequest.from_dict(payload, registry)
    except Exception as error:
        return f"{type(error).__name__}: {error}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--train", required=True)
    parser.add_argument("--heldout", required=True)
    parser.add_argument("--m1", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()

    registry = load_tool_registry(args.registry)
    train = read_jsonl(Path(args.train))
    eval_rows = [("heldout", row) for row in read_jsonl(Path(args.heldout))]
    eval_rows += [("m1_validation", row) for row in read_jsonl(Path(args.m1))]
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    predictions = {str(row["id"]): row for row in report["records"]}

    train_label_errors: list[dict[str, str]] = []
    train_catalog_missing = 0
    train_catalog_schema_drift = Counter()
    registry_tools = set(registry.names())
    for record in train:
        target = assistant_target(record)
        error = audit_label(target, registry)
        if error:
            train_label_errors.append({"id": str(record.get("id")), "error": error})
        catalog = record.get("tools")
        names = {
            str(item.get("function", {}).get("name"))
            for item in catalog
            if isinstance(item, Mapping)
        } if isinstance(catalog, list) else set()
        if names != registry_tools:
            train_catalog_missing += 1
        for item in catalog if isinstance(catalog, list) else []:
            function = item.get("function", {}) if isinstance(item, Mapping) else {}
            name = str(function.get("name", ""))
            if name not in registry_tools:
                continue
            embedded = function.get("parameters", {})
            current = registry.get(name).arguments_schema
            if embedded != current:
                train_catalog_schema_drift[name] += 1

    field_rows: list[dict[str, Any]] = []
    eval_label_errors: list[dict[str, str]] = []
    eval_catalog_present = 0
    for split, row in eval_rows:
        gold = row["chosen"]
        label_error = audit_label(gold, registry)
        if label_error:
            eval_label_errors.append({"id": str(row["id"]), "error": label_error})
        if prompt_mentions_catalog(row.get("prompt_messages", []), registry):
            eval_catalog_present += 1
        result = predictions[str(row["id"])]
        adapted = adapt_completion(result.get("completion", ""))
        predicted = adapted.payload if adapted.valid and adapted.payload else {}
        gold_calls = calls(gold)
        predicted_calls = calls(predicted)
        width = max(len(gold_calls), len(predicted_calls), 1)
        for index in range(width):
            gold_call = gold_calls[index] if index < len(gold_calls) else {}
            pred_call = predicted_calls[index] if index < len(predicted_calls) else {}
            gold_tool = str(gold_call.get("tool", ""))
            pred_tool = str(pred_call.get("tool", ""))
            pred_args = pred_call.get("arguments")
            pred_args = pred_args if isinstance(pred_args, Mapping) else {}
            gold_args = gold_call.get("arguments")
            gold_args = gold_args if isinstance(gold_args, Mapping) else {}
            allowed, required = schema_fields(registry, pred_tool)
            field_rows.append({
                "split": split,
                "id": str(row["id"]),
                "call_index": index,
                "gold_tool": gold_tool,
                "predicted_tool": pred_tool,
                "tool_match": gold_tool == pred_tool and bool(gold_tool),
                "missing_required": ",".join(sorted(required - set(pred_args))),
                "unknown_fields": ",".join(sorted(set(pred_args) - allowed)) if allowed else "",
                "missing_gold_fields": ",".join(sorted(set(gold_args) - set(pred_args))),
                "extra_vs_gold": ",".join(sorted(set(pred_args) - set(gold_args))),
                "matching_values": sum(pred_args.get(key) == value for key, value in gold_args.items()),
                "gold_field_count": len(gold_args),
                "strict_error_category": str(result.get("strict_error_category", "")),
            })

    counts = Counter()
    for row in field_rows:
        counts["calls"] += 1
        counts["tool_match"] += int(row["tool_match"])
        counts["tool_mismatch"] += int(not row["tool_match"])
        counts["missing_required_calls"] += int(bool(row["missing_required"]))
        counts["unknown_field_calls"] += int(bool(row["unknown_fields"]))
        counts["missing_gold_field_calls"] += int(bool(row["missing_gold_fields"]))
        counts["extra_vs_gold_calls"] += int(bool(row["extra_vs_gold"]))

    output = {
        "schema_version": "vaguehydro.tool_argument_audit.v1",
        "train": {
            "records": len(train),
            "label_valid": len(train) - len(train_label_errors),
            "label_errors": train_label_errors,
            "catalog_name_mismatch_records": train_catalog_missing,
            "embedded_schema_drift_records_by_tool": dict(train_catalog_schema_drift),
        },
        "evaluation": {
            "records": len(eval_rows),
            "label_valid": len(eval_rows) - len(eval_label_errors),
            "label_errors": eval_label_errors,
            "prompt_catalog_present": eval_catalog_present,
            "prompt_catalog_absent": len(eval_rows) - eval_catalog_present,
        },
        "predictions": dict(counts),
        "rows": field_rows,
    }
    Path(args.output_json).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with Path(args.output_csv).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(field_rows[0]))
        writer.writeheader()
        writer.writerows(field_rows)

    call_count = counts["calls"] or 1
    markdown = f"""# VagueHydro tool-argument audit

## Raw data table

| Check | Count | Rate |
|---|---:|---:|
| Targeted SFT labels valid under current registry | {len(train) - len(train_label_errors)}/{len(train)} | {(len(train) - len(train_label_errors))/len(train):.2%} |
| Fixed-B gold labels valid under current registry | {len(eval_rows) - len(eval_label_errors)}/{len(eval_rows)} | {(len(eval_rows) - len(eval_label_errors))/len(eval_rows):.2%} |
| Fixed-B prompts containing the tool catalog | {eval_catalog_present}/{len(eval_rows)} | {eval_catalog_present/len(eval_rows):.2%} |
| Predicted calls with correct tool at the same position | {counts['tool_match']}/{counts['calls']} | {counts['tool_match']/call_count:.2%} |
| Predicted calls missing required fields for predicted tool | {counts['missing_required_calls']}/{counts['calls']} | {counts['missing_required_calls']/call_count:.2%} |
| Predicted calls containing fields forbidden by predicted tool | {counts['unknown_field_calls']}/{counts['calls']} | {counts['unknown_field_calls']/call_count:.2%} |
| Predicted calls missing one or more gold fields | {counts['missing_gold_field_calls']}/{counts['calls']} | {counts['missing_gold_field_calls']/call_count:.2%} |
| Predicted calls adding fields absent from gold | {counts['extra_vs_gold_calls']}/{counts['calls']} | {counts['extra_vs_gold_calls']/call_count:.2%} |

## Key findings

1. Training and evaluation labels are checked directly with `AgentRequest.from_dict` and the frozen current registry; label failures are listed in the JSON artifact.
2. The fixed-B prompts are audited for the complete registry catalog. Absence is a train/evaluation prompt-contract mismatch because the SFT planner reconstructs prompts from each record's `tools` catalog.
3. Tool mismatch and argument-schema failures are reported separately. Exact-value agreement is not used as a substitute for schema validity.

## Suggested next experiment

Rebuild the same fixed 14-record evaluation prompts through the same planner prompt constructor used for SFT, preserving the frozen labels and model adapters. Re-evaluate v1/v2 without further training; only consider additional training after this controlled prompt-parity test.
"""
    Path(args.output_md).write_text(markdown, encoding="utf-8")
    print(json.dumps({key: output[key] for key in ("train", "evaluation", "predictions")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
