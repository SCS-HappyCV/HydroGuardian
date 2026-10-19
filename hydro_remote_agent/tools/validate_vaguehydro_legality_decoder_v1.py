from __future__ import annotations

import argparse
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from hydro_remote_agent.backbones.qwen3_vl_planner import planner_system_prompt
from hydro_remote_agent.data.sft import compact_tool_catalog
from hydro_remote_agent.legality_diagnostics import (
    classify_strict_error,
    count_values,
    parse_completion_object,
    request_signature,
)
from hydro_remote_agent.rewards.completion_adapter import adapt_completion
from hydro_remote_agent.tools.vaguehydro_legality_repair_core import generate_rows, load_eval, score_rows
from hydro_remote_agent.tools.vaguehydro_preference_pilot_core import (
    ROOT,
    load_freeze,
    load_model_and_processor,
    write_json,
)
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def with_full_text_tool_prompt(row: dict, cfg: dict) -> dict:
    registry = load_tool_registry(ROOT / str(cfg["tool_registry"]))
    source = {
        "id": row["id"],
        "messages": row["prompt_messages"],
        "tools": compact_tool_catalog(registry),
    }
    system = planner_system_prompt(source, prompt_profile="full")
    prompt_messages = [dict(message) for message in row["prompt_messages"]]
    for message in prompt_messages:
        if message.get("role") == "system":
            message["content"] = system
            break
    return {**row, "prompt_messages": prompt_messages}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--report-name", default="DECODER_REGRESSION_INITIAL.json")
    parser.add_argument("--include-diagnostics", action="store_true")
    parser.add_argument("--adapter", default=None)
    parser.add_argument(
        "--prompt-profile",
        choices=("legacy", "full_text_tools"),
        default="legacy",
    )
    args = parser.parse_args()
    run_dir = ROOT / args.run_dir
    cfg = load_freeze(run_dir)
    if Path(args.report_name).name != args.report_name or not args.report_name.endswith(".json"):
        raise ValueError("--report-name must be a JSON basename")
    report_path = run_dir / args.report_name
    if report_path.exists():
        raise FileExistsError(f"refusing to overwrite {report_path}")

    report = {
        "schema_version": "vaguehydro.decoder_regression.v1",
        "status": "running",
        "started_at": now(),
        "adapter": args.adapter or cfg["initial_sft_adapter"],
        "records": [],
        "frozen_240_reads": 0,
        "called_real_experts": False,
        "called_verifier": False,
        "formal_training": False,
        "diagnostics_included": bool(args.include_diagnostics),
        "prompt_profile": args.prompt_profile,
    }
    write_json(report_path, report)
    if args.adapter:
        cfg = dict(cfg)
        cfg["initial_sft_adapter"] = args.adapter
    model, processor = load_model_and_processor(cfg, trainable=False)
    started = time.monotonic()
    for split, filename in (("heldout", "heldout_eval.jsonl"), ("m1_validation", "m1_validation_eval.jsonl")):
        for row in load_eval(run_dir, filename):
            if args.prompt_profile == "full_text_tools":
                row = with_full_text_tool_prompt(row, cfg)
            item_started = time.monotonic()
            try:
                generated = generate_rows(model, processor.tokenizer, [row], cfg, True)
                metrics, details = score_rows(generated, [row], cfg)
                detail = details[0]
                item = {
                    "split": split,
                    "id": row["id"],
                    "status": "pass",
                    "decoder_exception": False,
                    "valid_prefix": bool((generated[0].get("constraint_state") or {}).get("valid_prefix")),
                    "strict_valid": bool(detail["strict_valid"]),
                    "clipped": bool(generated[0]["clipped"]),
                    "eos": bool(generated[0]["eos"]),
                    "reward_a": metrics["reward_a"]["total"],
                    "elapsed_seconds": round(time.monotonic() - item_started, 3),
                }
                if args.include_diagnostics:
                    adapted = adapt_completion(generated[0]["completion"])
                    diagnostic_payload = adapted.payload or parse_completion_object(
                        generated[0]["completion"]
                    )
                    item.update({
                        "completion": generated[0]["completion"],
                        "token_count": int(generated[0]["token_count"]),
                        "constraint_state": generated[0].get("constraint_state"),
                        "strict_error": detail.get("error"),
                        "strict_error_category": classify_strict_error(detail.get("error")),
                        "predicted_signature": request_signature(diagnostic_payload),
                        "gold_signature": request_signature(row.get("chosen")),
                        "reward_a_components": detail.get("reward_a"),
                        "reward_b_components": detail.get("reward_b"),
                    })
            except Exception as error:
                item = {
                    "split": split,
                    "id": row["id"],
                    "status": "fail",
                    "decoder_exception": True,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                    "elapsed_seconds": round(time.monotonic() - item_started, 3),
                }
            report["records"].append(item)
            write_json(report_path, report)
            if item["decoder_exception"]:
                report["status"] = "fail"
                report["finished_at"] = now()
                report["elapsed_seconds"] = round(time.monotonic() - started, 3)
                write_json(report_path, report)
                return 2
    report["status"] = "pass"
    report["finished_at"] = now()
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["all_14_without_decoder_exception"] = len(report["records"]) == 14
    report["summary"] = {}
    for split in ("heldout", "m1_validation"):
        rows = [item for item in report["records"] if item["split"] == split]
        report["summary"][split] = {
            "count": len(rows),
            "decoder_exceptions": sum(bool(item["decoder_exception"]) for item in rows),
            "strict_valid_rate": sum(bool(item.get("strict_valid")) for item in rows) / len(rows),
            "clipping_rate": sum(bool(item.get("clipped")) for item in rows) / len(rows),
            "reward_a_mean": sum(float(item.get("reward_a", 0.0)) for item in rows) / len(rows),
        }
        if args.include_diagnostics:
            report["summary"][split]["strict_error_categories"] = count_values(
                rows, "strict_error_category"
            )
            report["summary"][split]["predicted_action_types"] = count_values(
                [row["predicted_signature"] for row in rows], "action_type"
            )
            report["summary"][split]["gold_action_types"] = count_values(
                [row["gold_signature"] for row in rows], "action_type"
            )
    write_json(report_path, report)
    print(json.dumps({
        "status": report["status"],
        "records": len(report["records"]),
        "summary": report["summary"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
