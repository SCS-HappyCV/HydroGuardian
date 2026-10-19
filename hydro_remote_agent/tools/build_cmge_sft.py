from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from hydro_remote_agent.cmge_planner import (
    CMGE_SFT_SCHEMA_VERSION,
    _route_for_request,
    build_plan_target,
    canonical_json,
)
from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.build_cmge_conditions import read_jsonl, write_jsonl


def _compound_query(compound: Mapping[str, Any]) -> str:
    query = str(compound.get("query", "")).strip()
    if query:
        return query
    claims = compound.get("claims")
    if not isinstance(claims, list) or len(claims) != 2:
        raise ValueError(f"{compound.get('compound_id')} cannot reconstruct compound query")
    direct_query = str(claims[0].get("query", "")).strip()
    dense_query = str(claims[1].get("query", "")).strip()
    if not direct_query or not dense_query:
        raise ValueError(f"{compound.get('compound_id')} has empty component query")
    language = str(compound.get("language", "en"))
    if language.lower().startswith("zh"):
        return f"{direct_query.rstrip('？?')}；同时，{dense_query}"
    return f"{direct_query} Also, {dense_query}"


def _tool_catalog(registry) -> list[dict[str, Any]]:
    return [
        tool.to_openai_tool()
        for tool in sorted(registry.tools, key=lambda item: item.name)
    ]


def build_record(
    compound: Mapping[str, Any],
    registry,
    asset_root: str | None = None,
) -> Dict[str, Any]:
    target = build_plan_target(compound, asset_root)
    for claim in target["claims"]:
        AgentRequest.from_dict(claim["request"], registry)
    assets = compound.get("assets", {})
    if not isinstance(assets, Mapping):
        raise ValueError(f"{compound.get('compound_id')} assets must be an object")
    rewritten_assets = {
        str(key): _rewrite_path(str(value), asset_root)
        for key, value in assets.items()
        if isinstance(value, str) and value
    }
    images = [
        value
        for key, value in rewritten_assets.items()
        if key.endswith("image_path")
    ]
    point_clouds = [
        value
        for key, value in rewritten_assets.items()
        if key.endswith("point_cloud_path")
    ]
    if not images:
        raise ValueError(f"{compound.get('compound_id')} has no image asset")
    user_payload = {
        "compound_id": str(compound["compound_id"]),
        "query": _compound_query(compound),
        "language": str(compound.get("language", "en")),
        "assets": rewritten_assets,
    }
    dense_intent = str(compound["claims"][1].get("canonical_intent", ""))
    return {
        "schema_version": CMGE_SFT_SCHEMA_VERSION,
        "id": str(compound["compound_id"]),
        "compound_id": str(compound["compound_id"]),
        "sample_id": str(compound.get("sample_id", "")),
        "split": str(compound.get("split", "")),
        "language": str(compound.get("language", "en")),
        "messages": [
            {
                "role": "system",
                "content": "CMGE claim-wise planner input. The assistant must return a cmge.plan.v1 object.",
            },
            {"role": "user", "content": canonical_json(user_payload)},
            {"role": "assistant", "content": canonical_json(target)},
        ],
        "tools": _tool_catalog(registry),
        "images": images,
        "media": {"images": images, "point_clouds": point_clouds},
        "metadata": {
            "dense_intent": dense_intent,
            "claim_count": 2,
            "gold_routes": [
                _route_for_request(claim["request"])
                for claim in target["claims"]
            ],
        },
    }


def _rewrite_path(value: str, asset_root: str | None) -> str:
    if asset_root and "/benchmark/10M" in value:
        return asset_root.rstrip("/") + value.split("/benchmark/10M", 1)[1]
    return value


def build_dataset(
    compounds: Iterable[Mapping[str, Any]],
    registry,
    asset_root: str | None = None,
) -> tuple[list[Dict[str, Any]], dict[str, Any]]:
    records = [build_record(compound, registry, asset_root) for compound in compounds]
    route_counts = Counter(
        route
        for record in records
        for route in record["metadata"]["gold_routes"]
    )
    report = {
        "schema_version": "cmge.sft_report.v1",
        "record_count": len(records),
        "compound_count": len(records),
        "claim_count": len(records) * 2,
        "route_counts": dict(sorted(route_counts.items())),
        "asset_root": asset_root,
    }
    return records, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build CMGE claim-wise planner SFT JSONL.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--asset-root")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    compounds = read_jsonl(args.input)
    registry = load_tool_registry(args.registry)
    records, report = build_dataset(compounds, registry, args.asset_root)
    write_jsonl(args.output, records)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
