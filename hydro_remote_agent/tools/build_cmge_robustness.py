from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from hydro_remote_agent.evaluation.routing import iter_jsonl


VARIANTS = ("numbered", "first_then", "same_scene")


def _rewrite_ids(value: Any, source_id: str, target_id: str) -> Any:
    if isinstance(value, str):
        return value.replace(source_id, target_id)
    if isinstance(value, list):
        return [_rewrite_ids(item, source_id, target_id) for item in value]
    if isinstance(value, dict):
        return {
            key: _rewrite_ids(item, source_id, target_id)
            for key, item in value.items()
        }
    return value


def _query(variant: str, direct: str, dense: str) -> str:
    if variant == "numbered":
        return f"Please handle these two requests independently: (1) {direct} (2) {dense}"
    if variant == "first_then":
        return f"First, {direct} Then, {dense}"
    if variant == "same_scene":
        return f"For the same scene, answer this: {direct} In addition, {dense}"
    raise ValueError(f"Unsupported robustness variant: {variant}")


def build_robustness_records(
    sft_path: Path,
    manifest_path: Path,
    variants: Sequence[str] = VARIANTS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sft = {str(row["id"]): row for _, row in iter_jsonl(sft_path)}
    output: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for _, compound in iter_jsonl(manifest_path):
        source_id = str(compound["compound_id"])
        if source_id not in sft:
            raise ValueError(f"Missing SFT record for {source_id}")
        claims = compound.get("claims")
        if not isinstance(claims, list) or len(claims) != 2:
            raise ValueError(f"{source_id} must contain exactly two claims")
        direct = str(claims[0].get("query", "")).strip()
        dense = str(claims[1].get("query", "")).strip()
        if not direct or not dense:
            raise ValueError(f"{source_id} has an empty claim query")
        for variant in variants:
            target_id = f"{source_id}:robust_{variant}"
            record = _rewrite_ids(copy.deepcopy(sft[source_id]), source_id, target_id)
            record["id"] = target_id
            record["compound_id"] = target_id
            user_payload = json.loads(record["messages"][1]["content"])
            user_payload["compound_id"] = target_id
            user_payload["query"] = _query(variant, direct, dense)
            record["messages"][1]["content"] = json.dumps(
                user_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            metadata = dict(record.get("metadata", {}))
            metadata.update(
                {
                    "robustness_variant": variant,
                    "source_compound_id": source_id,
                }
            )
            record["metadata"] = metadata
            output.append(record)
            counts[variant] += 1
    report = {
        "schema_version": "cmge.robustness.v1",
        "source_compound_count": len(sft),
        "record_count": len(output),
        "variant_counts": dict(sorted(counts.items())),
        "variants": list(variants),
    }
    return output, report


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build deterministic CMGE language-robustness variants.")
    parser.add_argument("--sft", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--variant", action="append", choices=VARIANTS)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    variants = tuple(args.variant) if args.variant else VARIANTS
    rows, report = build_robustness_records(args.sft, args.manifest, variants)
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
