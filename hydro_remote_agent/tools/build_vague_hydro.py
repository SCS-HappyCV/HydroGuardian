from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.data.vague_hydro import (
    audit_asset_paths,
    audit_dataset,
    build_canonical_records,
    build_source_manifest,
    load_jsonl,
    load_split_assignments,
    parse_path_mappings,
    write_jsonl,
)
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build deterministic VagueHydro canonical data.")
    parser.add_argument(
        "--source-jsonl",
        default=str(
            PROJECT_ROOT
            / "data"
            / "wcs2d3d_lang_v4_llm_auto_cross_region_train_dashscope_en_v2.jsonl"
        ),
    )
    parser.add_argument(
        "--split-map",
        default=str(PROJECT_ROOT / "data" / "wcs10m_primary_split_map.json"),
    )
    parser.add_argument(
        "--registry",
        default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(PACKAGE_ROOT / "data" / "vague_hydro"),
    )
    parser.add_argument("--limit-tiles", type=int, default=0)
    parser.add_argument("--no-dense-variants", action="store_true")
    parser.add_argument("--no-full-scene-tasks", action="store_true")
    parser.add_argument(
        "--path-map",
        action="append",
        default=[],
        help="Asset path mapping in SRC=DST form; may be repeated.",
    )
    parser.add_argument("--require-assets", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    source_records = load_jsonl(args.source_jsonl)
    if args.limit_tiles > 0:
        source_records = source_records[: args.limit_tiles]
    split_assignments = load_split_assignments(args.split_map)
    if args.limit_tiles > 0:
        selected_ids = {str(record["sample_id"]) for record in source_records}
        split_assignments = {
            sample_id: split
            for sample_id, split in split_assignments.items()
            if sample_id in selected_ids
        }
    manifest = build_source_manifest(source_records, split_assignments)
    canonical = build_canonical_records(
        source_records,
        manifest,
        include_dense_variants=not args.no_dense_variants,
        include_full_scene_tasks=not args.no_full_scene_tasks,
    )
    registry = load_tool_registry(args.registry)
    report = audit_dataset(manifest, canonical, registry)
    report["asset_audit"] = audit_asset_paths(
        manifest,
        path_mappings=parse_path_mappings(args.path_map),
        require_all=bool(args.require_assets),
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "source_manifest.jsonl", manifest)
    write_jsonl(output_dir / "canonical_actions.jsonl", canonical)
    for split in ("train", "val", "test"):
        write_jsonl(
            output_dir / f"canonical_{split}.jsonl",
            (record for record in canonical if record["split"] == split),
        )
    with (output_dir / "audit_report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    with (output_dir / "dataset_stats.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "manifest_count": report["manifest_count"],
                "canonical_count": report["canonical_count"],
                "manifest_split_counts": report["manifest_split_counts"],
                "query_split_counts": report["query_split_counts"],
                "intent_counts": report["intent_counts"],
                "action_type_counts": report["action_type_counts"],
                "derivation_counts": report["derivation_counts"],
                "no_target_counts": report["no_target_counts"],
                "cross_split_exact_query_collision_count": report[
                    "cross_split_exact_query_collision_count"
                ],
                "asset_audit": report["asset_audit"],
            },
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")

    print(
        f"VAGUE_HYDRO_BUILD_OK manifest={len(manifest)} canonical={len(canonical)} "
        f"fingerprint={report['dataset_fingerprint']} output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
