from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from hydro_remote_agent.backbones.qwen3_vl_planner import canonical_json, read_jsonl
from hydro_remote_agent.evaluation.routing import extract_gold, sha256_file
from hydro_remote_agent.tools.run_agent_e2e_condition import _invocation_count


def _index(path: Path) -> Dict[str, Dict[str, Any]]:
    source_rows = read_jsonl(path)
    rows = {str(row.get("id", "")): dict(row) for row in source_rows}
    if "" in rows or len(rows) != len(source_rows):
        raise ValueError(f"{path} contains missing or duplicate request IDs")
    return rows


def merge_recorded_run(
    gold_path: Path,
    prediction_path: Path,
    execution_path: Path,
    output_path: Path,
    condition: str,
    expected_gold_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    gold_sha256 = sha256_file(gold_path)
    if expected_gold_sha256 and gold_sha256 != expected_gold_sha256:
        raise ValueError(
            f"Frozen gold SHA256 mismatch: expected {expected_gold_sha256}, got {gold_sha256}"
        )
    gold_records = read_jsonl(gold_path)
    gold_ids = [extract_gold(row)[0] for row in gold_records]
    if len(gold_ids) != len(set(gold_ids)):
        raise ValueError("Frozen gold contains duplicate request IDs")
    predictions = _index(prediction_path)
    executions = _index(execution_path)
    expected_ids = set(gold_ids)
    for name, rows in (("predictions", predictions), ("executions", executions)):
        if set(rows) != expected_ids:
            raise ValueError(
                f"{name} population mismatch: missing={sorted(expected_ids - set(rows))[:5]} "
                f"extra={sorted(set(rows) - expected_ids)[:5]}"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for request_id in gold_ids:
            prediction_row = predictions[request_id]
            execution_row = executions[request_id]
            result = execution_row.get("result")
            execution: Dict[str, Any] = {
                "id": request_id,
                "status": str(execution_row.get("status", "failed")),
            }
            if isinstance(result, Mapping):
                execution["result"] = dict(result)
            if execution_row.get("error") is not None:
                execution["error"] = execution_row["error"]

            inference = prediction_row.get("inference")
            inference = inference if isinstance(inference, Mapping) else {}
            batch_size = max(int(inference.get("batch_size", 1)), 1)
            planner_ms = float(inference.get("batch_seconds", 0.0)) * 1000.0 / batch_size
            execution_ms = (
                float(result.get("duration_ms", 0.0)) if isinstance(result, Mapping) else 0.0
            )
            row = {
                "id": request_id,
                "condition": condition,
                "prediction": prediction_row.get("prediction"),
                "execution": execution,
                "expert_invocation_count": _invocation_count(execution),
                "timing": {
                    "planner_ms": planner_ms,
                    "execution_ms": execution_ms,
                    "total_ms": planner_ms + execution_ms,
                    "model_load_excluded": True,
                    "planner_latency_scope": "per_request_estimate_from_offline_batch",
                },
                "generated_tokens": int(inference.get("generated_tokens", 0)),
                "trace": [
                    {
                        "round": 1,
                        "source": "frozen_planner_prediction_and_recorded_execution",
                        "prediction": prediction_row.get("prediction"),
                    }
                ],
                "provenance": {
                    "gold_sha256": gold_sha256,
                    "prediction_path": str(prediction_path),
                    "prediction_sha256": sha256_file(prediction_path),
                    "execution_path": str(execution_path),
                    "execution_sha256": sha256_file(execution_path),
                    "execution_replayed": False,
                },
            }
            handle.write(canonical_json(row) + "\n")

    return {
        "condition": condition,
        "request_count": len(gold_ids),
        "gold_sha256": gold_sha256,
        "prediction_sha256": sha256_file(prediction_path),
        "execution_sha256": sha256_file(execution_path),
        "output_sha256": sha256_file(output_path),
        "output": str(output_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge frozen Planner predictions and recorded executions into an E2E run."
    )
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--executions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--expected-gold-sha256")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = merge_recorded_run(
        gold_path=args.gold,
        prediction_path=args.predictions,
        execution_path=args.executions,
        output_path=args.output,
        condition=args.condition,
        expected_gold_sha256=args.expected_gold_sha256,
    )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"RECORDED_AGENT_E2E_MERGE_OK condition={args.condition} "
        f"requests={manifest['request_count']} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
