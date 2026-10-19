from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from hydro_remote_agent.tools.build_cmge_pilot import (
    DIRECT_INTENTS,
    DENSE_INTENTS,
    build_candidates,
    read_jsonl,
    stable_key,
    write_jsonl,
)


DEFAULT_DENSE_WEIGHTS = {
    "class_segmentation": 0.20,
    "attribute_segmentation": 0.35,
    "relation_segmentation": 0.45,
}


def _allocate(total: int, weights: Mapping[str, float]) -> Dict[str, int]:
    if total <= 0:
        raise ValueError("total must be positive")
    if not weights or any(value < 0 for value in weights.values()):
        raise ValueError("weights must be non-negative and non-empty")
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        raise ValueError("weights must sum to a positive value")
    raw = {key: total * value / weight_sum for key, value in weights.items()}
    counts = {key: int(value) for key, value in raw.items()}
    remainder = total - sum(counts.values())
    order = sorted(weights, key=lambda key: (raw[key] - counts[key], key), reverse=True)
    for key in order[:remainder]:
        counts[key] += 1
    return counts


def target_matrix(
    count: int,
    dense_weights: Mapping[str, float] = DEFAULT_DENSE_WEIGHTS,
) -> Dict[tuple[str, str], int]:
    dense_counts = _allocate(count, dense_weights)
    direct_intents = sorted(DIRECT_INTENTS)
    matrix: Dict[tuple[str, str], int] = {}
    for dense_intent, dense_count in dense_counts.items():
        direct_counts = _allocate(
            dense_count,
            {intent: 1.0 for intent in direct_intents},
        )
        for direct_intent, direct_count in direct_counts.items():
            matrix[(direct_intent, dense_intent)] = direct_count
    return matrix


def select_targeted(
    candidates: Sequence[Mapping[str, Any]],
    count: int,
    seed: int,
    max_per_tile: int,
    dense_weights: Mapping[str, float] = DEFAULT_DENSE_WEIGHTS,
) -> list[Dict[str, Any]]:
    if max_per_tile <= 0:
        raise ValueError("max_per_tile must be positive")
    remaining = target_matrix(count, dense_weights)
    buckets: Dict[tuple[str, str], list[Dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        claims = candidate.get("claims")
        if not isinstance(claims, list) or len(claims) != 2:
            continue
        key = (
            str(claims[0].get("canonical_intent", "")),
            str(claims[1].get("canonical_intent", "")),
        )
        if key[0] in DIRECT_INTENTS and key[1] in DENSE_INTENTS:
            buckets[key].append(dict(candidate))
    for key, values in buckets.items():
        values.sort(
            key=lambda item: stable_key(f"targeted:{key}:{item['compound_id']}", seed),
            reverse=True,
        )

    selected: list[Dict[str, Any]] = []
    selected_ids: set[str] = set()
    tile_counts: Counter[str] = Counter()
    while len(selected) < count:
        feasible_keys = [
            key
            for key, values in buckets.items()
            if values and remaining[key] > 0
        ]
        if not feasible_keys:
            missing = {str(key): value for key, value in remaining.items() if value > 0}
            raise ValueError(f"unable to satisfy targeted matrix quotas: {missing}")
        feasible_keys.sort(
            key=lambda key: (
                len(buckets[key]) / remaining[key],
                len(buckets[key]),
                stable_key(str(key), seed),
            ),
        )
        progress = False
        for key in feasible_keys:
            while buckets[key]:
                candidate = buckets[key].pop()
                compound_id = str(candidate.get("compound_id", ""))
                sample_id = str(candidate.get("sample_id", ""))
                if compound_id in selected_ids or tile_counts[sample_id] >= max_per_tile:
                    continue
                selected.append(candidate)
                selected_ids.add(compound_id)
                tile_counts[sample_id] += 1
                remaining[key] -= 1
                progress = True
                break
            if progress:
                break
        if not progress:
            missing = {str(key): value for key, value in remaining.items() if value > 0}
            raise ValueError(f"tile cap prevents targeted matrix quotas: {missing}")
    selected.sort(key=lambda item: stable_key(str(item["compound_id"]), seed))
    return selected


def targeted_report(
    candidates: Sequence[Mapping[str, Any]],
    selected: Sequence[Mapping[str, Any]],
    count: int,
    max_per_tile: int,
    dense_weights: Mapping[str, float],
) -> Dict[str, Any]:
    direct_counts = Counter(str(row["claims"][0]["canonical_intent"]) for row in selected)
    dense_counts = Counter(str(row["claims"][1]["canonical_intent"]) for row in selected)
    pair_counts = Counter(
        f"{row['claims'][0]['canonical_intent']} + {row['claims'][1]['canonical_intent']}"
        for row in selected
    )
    tile_counts = Counter(str(row["sample_id"]) for row in selected)
    return {
        "schema_version": "cmge.targeted.v1",
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "requested_count": count,
        "unique_tiles": len(tile_counts),
        "max_selected_per_tile": max(tile_counts.values(), default=0),
        "max_per_tile": max_per_tile,
        "dense_weights": dict(dense_weights),
        "direct_intent_counts": dict(sorted(direct_counts.items())),
        "dense_intent_counts": dict(sorted(dense_counts.items())),
        "intent_pair_counts": dict(sorted(pair_counts.items())),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Gate500-D targeted CMGE compounds.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--count", type=int, default=4000)
    parser.add_argument("--max-per-tile", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260824)
    parser.add_argument("--class-weight", type=float, default=0.20)
    parser.add_argument("--attribute-weight", type=float, default=0.35)
    parser.add_argument("--relation-weight", type=float, default=0.45)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    weights = {
        "class_segmentation": args.class_weight,
        "attribute_segmentation": args.attribute_weight,
        "relation_segmentation": args.relation_weight,
    }
    rows = read_jsonl(args.input)
    candidates = build_candidates(rows, args.seed)
    selected = select_targeted(
        candidates,
        args.count,
        args.seed,
        args.max_per_tile,
        weights,
    )
    report = targeted_report(candidates, selected, args.count, args.max_per_tile, weights)
    write_jsonl(args.output, selected)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
