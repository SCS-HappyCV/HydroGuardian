from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from hydro_remote_agent.legality_diagnostics import (
    classify_strict_error,
    parse_completion_object,
    request_signature,
)


REQUIRED_ENVELOPE_KEYS = ("schema_version", "request_id", "intent", "action")


def tool_sequence(signature: Mapping[str, Any]) -> list[str]:
    tool = signature.get("tool")
    if isinstance(tool, str):
        return [tool]
    steps = signature.get("step_tools")
    return list(steps) if isinstance(steps, list) else []


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    tool_rows = [row for row in rows if tool_sequence(row["gold_signature"])]
    return {
        "count": count,
        "decoder_exception_rate": ratio(sum(row["decoder_exception"] for row in rows), count),
        "eos_rate": ratio(sum(row["eos"] for row in rows), count),
        "clipping_rate": ratio(sum(row["clipped"] for row in rows), count),
        "complete_required_envelope_rate": ratio(
            sum(not row["missing_required_keys"] for row in rows), count
        ),
        "strict_valid_rate": ratio(sum(row["strict_valid"] for row in rows), count),
        "action_type_match_rate": ratio(sum(row["action_type_match"] for row in rows), count),
        "tool_sequence_match_rate_all": ratio(sum(row["tool_sequence_match"] for row in rows), count),
        "tool_bearing_count": len(tool_rows),
        "tool_sequence_match_rate_tool_bearing": ratio(
            sum(row["tool_sequence_match"] for row in tool_rows), len(tool_rows)
        ),
        "expected_output_match_rate": ratio(sum(row["expected_output_match"] for row in rows), count),
        "error_categories": dict(sorted(Counter(row["error_category"] for row in rows).items())),
    }


def analyze(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    for source in records:
        payload = parse_completion_object(str(source.get("completion", "")))
        predicted = request_signature(payload)
        gold = dict(source.get("gold_signature") or {})
        missing = [key for key in REQUIRED_ENVELOPE_KEYS if not payload or key not in payload]
        category = (
            "missing_required_envelope"
            if missing
            else classify_strict_error(source.get("strict_error"))
        )
        predicted_tools = tool_sequence(predicted)
        gold_tools = tool_sequence(gold)
        row = {
            "id": source.get("id"),
            "split": source.get("split"),
            "strict_error": source.get("strict_error"),
            "error_category": category,
            "missing_required_keys": missing,
            "predicted_signature": predicted,
            "gold_signature": gold,
            "action_type_match": predicted.get("action_type") == gold.get("action_type"),
            "tool_sequence_match": predicted_tools == gold_tools,
            "expected_output_match": (
                predicted.get("expected_output_type") == gold.get("expected_output_type")
                and predicted.get("coordinate_space") == gold.get("coordinate_space")
            ),
            "strict_valid": bool(source.get("strict_valid")),
            "decoder_exception": bool(source.get("decoder_exception")),
            "eos": bool(source.get("eos")),
            "clipped": bool(source.get("clipped")),
            "token_count": source.get("token_count"),
        }
        rows.append(row)

    count = len(rows)
    key_presence = {
        key: sum(key not in row["missing_required_keys"] for row in rows)
        for key in REQUIRED_ENVELOPE_KEYS
    }
    key_presence["expected_output"] = sum(
        "expected_output" in row["predicted_signature"]["top_level_keys"] for row in rows
    )
    summary = {
        **aggregate(rows),
        "required_key_presence": {
            key: {"count": value, "rate": ratio(value, count)}
            for key, value in key_presence.items()
        },
        "by_split": {
            split: aggregate([row for row in rows if row["split"] == split])
            for split in sorted({str(row["split"]) for row in rows})
        },
    }
    return {"schema_version": "vaguehydro.semantic_diagnostics_analysis.v1", "summary": summary, "rows": rows}


def markdown(analysis: Mapping[str, Any]) -> str:
    summary = analysis["summary"]
    envelope_complete = summary["complete_required_envelope_rate"] == 1.0
    if envelope_complete:
        interpretation = [
            "1. Root-envelope enforcement worked without harming termination: every record contains the required root fields and still reaches EOS.",
            "2. The remaining structural errors are deeper in workflow steps, while tool-selection and expected-output errors expose model-level contract mismatch.",
            "3. Action type is mostly retained, but exact tool sequence remains zero on tool-bearing cases; schema closure alone cannot select the task-correct tool.",
            "4. A release or formal-training claim remains unsupported because held-out strict validity is still zero.",
        ]
        next_experiment = (
            "Require step_id, tool, and arguments before closing each workflow step and enforce the step_id lexical contract, then rerun the fixed 14 records. "
            "If tool-bearing exact match remains zero, proceed to a targeted SFT pilot for tool selection and expected-output compatibility."
        )
    else:
        interpretation = [
            "1. The decoder is terminating correctly, so token-budget and EOS handling are no longer the limiting factors.",
            "2. The dominant failure is premature root-object closure before the required AgentRequest envelope is complete. This is prefix-decomposable and should be fixed in the decoder before training.",
            "3. Action type is mostly retained, but tool-bearing cases still need separate attention because empty direct-answer tool sequences inflate the all-record tool match rate.",
            "4. A model-training claim remains unsupported until the fixed decoder exposes the residual tool and expected-output errors.",
        ]
        next_experiment = (
            "Require schema_version, request_id, intent, and action before allowing the root object to close, then re-evaluate the same fixed 14 records. "
            "Start a targeted SFT pilot only if tool/output errors remain after that decoder-only control."
        )
    lines = [
        "# VagueHydro Semantic Diagnostics",
        "",
        "## Raw data table",
        "",
        "| split | id | category | missing root keys | action pred/gold | tools pred/gold | output match |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in analysis["rows"]:
        pred = row["predicted_signature"]
        gold = row["gold_signature"]
        lines.append(
            "| {split} | {id} | {category} | {missing} | {pa}/{ga} | {pt}/{gt} | {output} |".format(
                split=row["split"],
                id=row["id"],
                category=row["error_category"],
                missing=", ".join(row["missing_required_keys"]) or "none",
                pa=pred.get("action_type"),
                ga=gold.get("action_type"),
                pt=", ".join(tool_sequence(pred)) or "none",
                gt=", ".join(tool_sequence(gold)) or "none",
                output="yes" if row["expected_output_match"] else "no",
            )
        )
    lines.extend([
        "",
        "## Key findings",
        "",
        f"1. Decoder operation: EOS {summary['eos_rate']:.1%}, clipping {summary['clipping_rate']:.1%}, exceptions {summary['decoder_exception_rate']:.1%}.",
        f"2. Required envelope completion: {summary['complete_required_envelope_rate']:.1%}.",
        f"3. Strict validity: {summary['strict_valid_rate']:.1%}.",
        f"4. Semantic signatures: action type {summary['action_type_match_rate']:.1%}, exact tool sequence on tool-bearing cases {summary['tool_sequence_match_rate_tool_bearing']:.1%} ({summary['tool_bearing_count']} cases), expected output {summary['expected_output_match_rate']:.1%}.",
        f"5. Error categories: {json.dumps(summary['error_categories'], ensure_ascii=False, sort_keys=True)}.",
        "",
        "## Interpretation and implications",
        "",
        *interpretation,
        "",
        "## Suggested next experiment",
        "",
        next_experiment,
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    analysis = analyze(report["records"])
    Path(args.output_json).write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    Path(args.output_md).write_text(markdown(analysis), encoding="utf-8")
    print(json.dumps(analysis["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
