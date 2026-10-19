from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


DIRECT_INTENTS = {
    "class_presence",
    "attribute_judgement",
    "relation_judgement",
}
DENSE_INTENTS = {
    "class_segmentation",
    "attribute_segmentation",
    "relation_segmentation",
}


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{line_number} must contain an object")
                rows.append(value)
    return rows


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def stable_key(value: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode("utf-8")).hexdigest()


def _source_id(row: Mapping[str, Any]) -> str:
    provenance = row.get("provenance")
    if isinstance(provenance, Mapping):
        return str(provenance.get("source_text_id", ""))
    return ""


def _component(row: Mapping[str, Any], role: str) -> Dict[str, Any]:
    return {
        "role": role,
        "query_id": str(row.get("query_id", "")),
        "query": str(row.get("query", "")),
        "canonical_intent": str(row.get("canonical_intent", "")),
        "output_granularity": str(row.get("output_granularity", "")),
        "gold_request": row.get("gold_request", {}),
        "supervision": row.get("supervision", {}),
    }


def _asset_paths(row: Mapping[str, Any]) -> Dict[str, str]:
    request = row.get("gold_request")
    action = request.get("action") if isinstance(request, Mapping) else None
    arguments = action.get("arguments") if isinstance(action, Mapping) else None
    if isinstance(arguments, Mapping):
        return {
            "image_path": str(arguments.get("image_path", "")),
            "point_cloud_path": str(arguments.get("point_cloud_path", "")),
        }
    steps = action.get("steps") if isinstance(action, Mapping) else None
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            step_arguments = step.get("arguments")
            if isinstance(step_arguments, Mapping) and step_arguments.get("point_cloud_path"):
                return {
                    "image_path": str(step_arguments.get("image_path", "")),
                    "point_cloud_path": str(step_arguments.get("point_cloud_path", "")),
                }
    return {"image_path": "", "point_cloud_path": ""}


def _compound_query(direct_query: str, dense_query: str, language: str) -> str:
    direct = direct_query.strip()
    dense = dense_query.strip()
    if language.lower().startswith("zh"):
        return f"{direct.rstrip('？?')}；同时，{dense}"
    return f"{direct} Also, {dense}"


def build_candidates(
    rows: Sequence[Mapping[str, Any]],
    seed: int,
    allowed_sample_ids: set[str] | None = None,
    excluded_sample_ids: set[str] | None = None,
) -> List[Dict[str, Any]]:
    by_sample: Dict[str, Dict[str, List[Mapping[str, Any]]]] = defaultdict(
        lambda: {"direct": [], "dense": []}
    )
    for row in rows:
        intent = str(row.get("canonical_intent", ""))
        sample_id = str(row.get("sample_id", ""))
        if allowed_sample_ids is not None and sample_id not in allowed_sample_ids:
            continue
        if excluded_sample_ids is not None and sample_id in excluded_sample_ids:
            continue
        if not sample_id:
            continue
        if intent in DIRECT_INTENTS:
            by_sample[sample_id]["direct"].append(row)
        elif intent in DENSE_INTENTS:
            by_sample[sample_id]["dense"].append(row)

    candidates: List[Dict[str, Any]] = []
    for sample_id, groups in by_sample.items():
        direct_rows = sorted(groups["direct"], key=lambda row: str(row.get("query_id", "")))
        dense_rows = sorted(groups["dense"], key=lambda row: str(row.get("query_id", "")))
        for direct in direct_rows:
            for dense in dense_rows:
                if _source_id(direct) == _source_id(dense):
                    continue
                split = str(direct.get("split", ""))
                if split != str(dense.get("split", "")):
                    continue
                pair_id = f"{sample_id}:{direct.get('query_id')}:{dense.get('query_id')}"
                assets = _asset_paths(dense)
                candidates.append(
                    {
                        "schema_version": "cmge.pilot.v1",
                        "compound_id": f"cmge:{sample_id}:{stable_key(pair_id, seed)[:12]}",
                        "sample_id": sample_id,
                        "split": split,
                        "language": str(direct.get("language", "en")),
                        "query": _compound_query(
                            str(direct.get("query", "")),
                            str(dense.get("query", "")),
                            str(direct.get("language", "en")),
                        ),
                        "claims": [
                            _component(direct, "semantic_judgement"),
                            _component(dense, "dense_localization"),
                        ],
                        "assets": assets,
                    }
                )
    return candidates


def select_balanced(
    candidates: Sequence[Mapping[str, Any]],
    count: int,
    seed: int,
    max_per_tile: int | None = None,
) -> List[Dict[str, Any]]:
    if max_per_tile is not None and max_per_tile <= 0:
        raise ValueError("max_per_tile must be positive")
    buckets: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        claims = candidate["claims"]
        key = (str(candidate.get("split", "")), str(claims[1].get("canonical_intent", "")))
        buckets[key].append(dict(candidate))
    for values in buckets.values():
        values.sort(key=lambda item: stable_key(str(item["compound_id"]), seed))

    selected: List[Dict[str, Any]] = []
    tile_counts: Counter[str] = Counter()
    keys = sorted(buckets)
    while len(selected) < count and keys:
        remaining: List[tuple[str, str]] = []
        for key in keys:
            while buckets[key] and len(selected) < count:
                candidate = buckets[key].pop()
                sample_id = str(candidate.get("sample_id", ""))
                if max_per_tile is not None and tile_counts[sample_id] >= max_per_tile:
                    continue
                selected.append(candidate)
                tile_counts[sample_id] += 1
                break
            if buckets[key]:
                remaining.append(key)
        keys = remaining
    return selected


def structural_report(candidates: Sequence[Mapping[str, Any]], selected: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    dense_intents = Counter(str(item["claims"][1].get("canonical_intent", "")) for item in selected)
    splits = Counter(str(item.get("split", "")) for item in selected)
    samples = {str(item.get("sample_id", "")) for item in selected}
    claim_count = len(selected) * 2
    direct_claim_count = len(selected)
    dense_claim_count = len(selected)
    return {
        "schema_version": "cmge.pilot_report.v1",
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "unique_selected_tiles": len(samples),
        "selected_by_split": dict(sorted(splits.items())),
        "selected_dense_intents": dict(sorted(dense_intents.items())),
        "claims_per_request": 2,
        "whole_request_baseline_claim_coverage": {
            "direct_only": direct_claim_count / claim_count if claim_count else 0.0,
            "dense_only": dense_claim_count / claim_count if claim_count else 0.0,
            "cmge_oracle": 1.0 if selected else 0.0,
        },
        "baseline_warning": (
            "These are claim-coverage upper bounds, not model accuracy. A whole-request "
            "baseline is counted as incomplete when it emits only one claim type."
        ),
        "interpretation": (
            "Structural coverage only. CMGE oracle is not a model result; it establishes "
            "that both claim types can be evaluated on the same tile."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the CMGE compound-request structural pilot.")
    parser.add_argument("--input", required=True, type=Path, nargs="+")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument(
        "--max-per-tile",
        type=int,
        help="Optional cap on selected compound requests from one tile.",
    )
    parser.add_argument(
        "--reference-gold",
        type=Path,
        help="Optional frozen planner gold JSONL; restrict components to its tile population.",
    )
    parser.add_argument(
        "--exclude-reference",
        type=Path,
        help="Optional JSONL whose sample_id tiles must be excluded from the pilot.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.count <= 0:
        raise ValueError("--count must be positive")
    rows: List[Dict[str, Any]] = []
    for input_path in args.input:
        rows.extend(read_jsonl(input_path))
    allowed_sample_ids = None
    if args.reference_gold:
        allowed_sample_ids = {
            str(row.get("sample_id", ""))
            for row in read_jsonl(args.reference_gold)
            if row.get("sample_id")
        }
    excluded_sample_ids = None
    if args.exclude_reference:
        excluded_sample_ids = {
            str(row.get("sample_id", ""))
            for row in read_jsonl(args.exclude_reference)
            if row.get("sample_id")
        }
    candidates = build_candidates(
        rows,
        args.seed,
        allowed_sample_ids,
        excluded_sample_ids,
    )
    selected = select_balanced(candidates, args.count, args.seed, args.max_per_tile)
    report = structural_report(candidates, selected)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "compound_requests.jsonl", selected)
    (args.output_dir / "pilot_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
