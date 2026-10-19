from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from hydro_remote_agent.data.sft import format_sft_dataset
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Format frozen VagueHydro data for SFT.")
    parser.add_argument("--config", default=None)
    parser.add_argument(
        "--input-dir",
        default=str(PACKAGE_ROOT / "data" / "vague_hydro_generated"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(PACKAGE_ROOT / "data" / "vague_hydro_sft"),
    )
    parser.add_argument(
        "--source-manifest",
        default=str(PACKAGE_ROOT / "data" / "vague_hydro" / "source_manifest.jsonl"),
    )
    parser.add_argument(
        "--registry",
        default=str(PACKAGE_ROOT / "configs" / "tool_registry.yaml"),
    )
    parser.add_argument(
        "--ontology",
        default=str(PACKAGE_ROOT / "data" / "schema" / "ontology.json"),
    )
    parser.add_argument(
        "--path-map",
        action="append",
        default=[],
        help="Rewrite asset prefixes as SOURCE=TARGET; may be repeated.",
    )
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", default=None)
    pre_args, _ = pre_parser.parse_known_args(argv)
    parser = build_parser()
    if pre_args.config:
        with Path(pre_args.config).open("r", encoding="utf-8") as handle:
            config: Dict[str, Any] = json.load(handle)
        parser.set_defaults(**config)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    with Path(args.ontology).open("r", encoding="utf-8") as handle:
        ontology = json.load(handle)
    if not isinstance(ontology, dict):
        raise ValueError("ontology must contain a JSON object")
    path_maps = []
    for item in args.path_map:
        if "=" not in item:
            raise ValueError(f"invalid --path-map {item!r}; expected SOURCE=TARGET")
        source, target = item.split("=", 1)
        if not source.strip() or not target.strip():
            raise ValueError(f"invalid --path-map {item!r}; prefixes cannot be empty")
        path_maps.append((source.strip(), target.strip()))
    report = format_sft_dataset(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        source_manifest_path=Path(args.source_manifest),
        ontology=ontology,
        registry=load_tool_registry(args.registry),
        path_maps=path_maps,
    )
    print(
        f"VAGUE_HYDRO_SFT_OK records={report['record_count']} "
        f"fingerprint={report['dataset_fingerprint']} output={args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
