from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from hydro_remote_agent.tools.build_cmge_conditions import (
    build_conditions,
    read_jsonl,
    write_jsonl,
    write_manifest,
)


SOURCE_TOOL = "language_guided_point_segmentation"
SUPPORTED_INTENTS = ("class_segmentation", "attribute_segmentation")


def _stable_key(compound: Mapping[str, Any], seed: int) -> str:
    value = f"{seed}:{compound['compound_id']}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _dense_intent(compound: Mapping[str, Any]) -> str:
    return str(compound["claims"][1].get("canonical_intent", ""))


def _uses_source_tool(compound: Mapping[str, Any]) -> bool:
    action = compound["claims"][1].get("gold_request", {}).get("action", {})
    return action.get("type") == "tool_call" and action.get("tool") == SOURCE_TOOL


def select_calibration_compounds(
    compounds: Iterable[Mapping[str, Any]],
    per_intent: int,
    seed: int,
) -> list[dict[str, Any]]:
    if per_intent <= 0:
        raise ValueError("per_intent must be positive")
    buckets: dict[str, dict[str, list[dict[str, Any]]]] = {
        intent: defaultdict(list) for intent in SUPPORTED_INTENTS
    }
    seen_samples: set[str] = set()
    for raw in compounds:
        compound = dict(raw)
        intent = _dense_intent(compound)
        sample_id = str(compound.get("sample_id", ""))
        if intent not in buckets or not _uses_source_tool(compound) or sample_id in seen_samples:
            continue
        seen_samples.add(sample_id)
        region = sample_id.split("_", 1)[0]
        buckets[intent][region].append(compound)

    selected: list[dict[str, Any]] = []
    for intent in SUPPORTED_INTENTS:
        region_rows = buckets[intent]
        for rows in region_rows.values():
            rows.sort(key=lambda row: _stable_key(row, seed))
        region_order = sorted(region_rows)
        intent_rows: list[dict[str, Any]] = []
        while len(intent_rows) < per_intent:
            progressed = False
            for region in region_order:
                if region_rows[region]:
                    intent_rows.append(region_rows[region].pop(0))
                    progressed = True
                    if len(intent_rows) == per_intent:
                        break
            if not progressed:
                raise ValueError(
                    f"Only {len(intent_rows)} unique {intent} samples are available; "
                    f"requested {per_intent}"
                )
        selected.extend(intent_rows)
    return sorted(selected, key=lambda row: str(row["compound_id"]))


def build_calibration_dataset(
    input_path: Path,
    output_dir: Path,
    per_intent: int,
    seed: int,
    asset_root: Optional[str],
) -> dict[str, Any]:
    selected = select_calibration_compounds(read_jsonl(input_path), per_intent, seed)
    claimwise = build_conditions(selected, asset_root)["claimwise_rule_decomposition"]
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "compound_requests.jsonl", selected)
    write_manifest(output_dir / "compound_manifest.jsonl", selected)
    write_jsonl(output_dir / "baseline_predictions.jsonl", claimwise)

    sample_ids = [str(row["sample_id"]) for row in selected]
    report = {
        "schema_version": "cmge.capability_calibration_set.v1",
        "source_split": sorted({str(row.get("split", "")) for row in selected}),
        "source_tool": SOURCE_TOOL,
        "seed": seed,
        "compound_count": len(selected),
        "unique_sample_count": len(set(sample_ids)),
        "intent_counts": dict(sorted(Counter(_dense_intent(row) for row in selected).items())),
        "region_counts": dict(sorted(Counter(value.split("_", 1)[0] for value in sample_ids).items())),
        "sample_id_sha256": hashlib.sha256("\n".join(sorted(sample_ids)).encode("utf-8")).hexdigest(),
        "test_data_used_for_selection": False,
    }
    (output_dir / "calibration_set_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a split-safe CMGE capability calibration set.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--per-intent", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--asset-root")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_calibration_dataset(
        args.input, args.output_dir, args.per_intent, args.seed, args.asset_root
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
