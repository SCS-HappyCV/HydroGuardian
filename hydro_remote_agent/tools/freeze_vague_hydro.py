from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from hydro_remote_agent.data.sft import freeze_generated_dataset


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze an audited VagueHydro dataset.")
    parser.add_argument(
        "--generated-dir",
        default=str(PACKAGE_ROOT / "data" / "vague_hydro_generated"),
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
    parser.add_argument("--output", default=None)
    parser.add_argument("--provenance-file", action="append", default=[])
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    generated_dir = Path(args.generated_dir)
    output_path = (
        Path(args.output) if args.output else generated_dir / "freeze_manifest.json"
    )
    manifest = freeze_generated_dataset(
        generated_dir=generated_dir,
        source_manifest_path=Path(args.source_manifest),
        registry_path=Path(args.registry),
        ontology_path=Path(args.ontology),
        extra_provenance_files=[Path(path) for path in args.provenance_file],
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        f"VAGUE_HYDRO_FREEZE_OK records={manifest['record_count']} "
        f"fingerprint={manifest['dataset_fingerprint']} output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
