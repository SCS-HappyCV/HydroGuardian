from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from hydro_remote_agent.cmge_planner import CMGE_PLAN_SCHEMA_VERSION
from hydro_remote_agent.evaluation.routing import iter_jsonl, parse_json_response
from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


def expand_predictions(
    prediction_path: Path,
    registry_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    registry = load_tool_registry(registry_path)
    output: list[dict[str, Any]] = []
    route_counts: Counter[str] = Counter()
    compound_count = 0
    for line_number, row in iter_jsonl(prediction_path):
        compound_id = str(row.get("id") or row.get("compound_id") or "")
        if not compound_id:
            raise ValueError(f"{prediction_path}:{line_number} is missing compound id")
        plan = parse_json_response(row.get("prediction"))
        if plan.get("schema_version") != CMGE_PLAN_SCHEMA_VERSION:
            raise ValueError(f"{compound_id} has invalid CMGE schema version")
        if str(plan.get("compound_id", "")) != compound_id:
            raise ValueError(f"{compound_id} plan compound_id does not match its row id")
        claims = plan.get("claims")
        if not isinstance(claims, list) or len(claims) != 2:
            raise ValueError(f"{compound_id} must contain exactly two claims")
        by_index = {
            int(claim.get("claim_index", -1)): claim
            for claim in claims
            if isinstance(claim, Mapping)
        }
        if set(by_index) != {0, 1}:
            raise ValueError(f"{compound_id} must contain claim indices 0 and 1")
        for claim_index in (0, 1):
            claim = by_index[claim_index]
            request_payload = claim.get("request")
            if not isinstance(request_payload, Mapping):
                raise ValueError(f"{compound_id}:claim{claim_index} request must be an object")
            request = AgentRequest.from_dict(dict(request_payload), registry)
            expected_id = f"{compound_id}:claim{claim_index}"
            if request.request_id != expected_id:
                raise ValueError(
                    f"{compound_id}:claim{claim_index} request_id must be {expected_id!r}"
                )
            route = str(claim.get("route", ""))
            route_counts[route] += 1
            output.append(
                {
                    "id": expected_id,
                    "compound_id": compound_id,
                    "claim_index": claim_index,
                    "claim_role": str(claim.get("role", "")),
                    "intent": str(claim.get("intent", "")),
                    "route": route,
                    "prediction": dict(request_payload),
                }
            )
        compound_count += 1
    report = {
        "schema_version": "cmge.execution_expansion.v1",
        "compound_count": compound_count,
        "claim_count": len(output),
        "route_counts": dict(sorted(route_counts.items())),
    }
    return output, report


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Expand CMGE plans into executable AgentRequest rows.")
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    rows, report = expand_predictions(args.predictions, args.registry)
    write_jsonl(args.output, rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
