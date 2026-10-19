from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
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


def write_condition_subset(
    input_path: Path,
    output_dir: Path,
    count: int,
) -> dict[str, int]:
    compounds = read_jsonl(input_path)
    if count <= 0:
        raise ValueError("count must be positive")
    selected = compounds[:count]
    conditions = build_conditions(selected)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in conditions.items():
        write_jsonl(output_dir / name / "predictions.jsonl", rows)
    write_manifest(output_dir / "compound_manifest.jsonl", selected)
    return {name: len(rows) for name, rows in conditions.items()}


def _rewrite_paths(value: Any, asset_root: str | None) -> Any:
    if asset_root is None:
        return value
    if isinstance(value, str):
        marker = "/benchmark/10M"
        if marker in value:
            suffix = value.split(marker, 1)[1]
            return asset_root.rstrip("/") + suffix
        return value
    if isinstance(value, list):
        return [_rewrite_paths(item, asset_root) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_paths(item, asset_root) for key, item in value.items()}
    return value


def _request_for_claim(
    compound: Mapping[str, Any],
    index: int,
    asset_root: str | None = None,
) -> dict[str, Any]:
    claim = compound["claims"][index]
    request = _rewrite_paths(copy.deepcopy(claim["gold_request"]), asset_root)
    request["request_id"] = f"{compound['compound_id']}:claim{index}"
    return request


def _prediction_row(
    compound: Mapping[str, Any],
    index: int,
    asset_root: str | None = None,
) -> dict[str, Any]:
    request = _request_for_claim(compound, index, asset_root)
    return {
        "id": request["request_id"],
        "prediction": request,
        "compound_id": str(compound["compound_id"]),
        "claim_index": index,
        "claim_role": str(compound["claims"][index].get("role", "")),
    }


def build_conditions(
    compounds: Iterable[Mapping[str, Any]],
    asset_root: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    conditions = {
        "direct_only": [],
        "dense_only": [],
        "claimwise_rule_decomposition": [],
    }
    for compound in compounds:
        claims = compound.get("claims")
        if not isinstance(claims, list) or len(claims) != 2:
            raise ValueError(f"{compound.get('compound_id')} must contain exactly two claims")
        direct = _prediction_row(compound, 0, asset_root)
        dense = _prediction_row(compound, 1, asset_root)
        direct_baseline = dict(direct)
        direct_baseline["id"] = str(compound["compound_id"])
        direct_baseline["prediction"] = dict(direct["prediction"])
        direct_baseline["prediction"]["request_id"] = str(compound["compound_id"])
        dense_baseline = dict(dense)
        dense_baseline["id"] = str(compound["compound_id"])
        dense_baseline["prediction"] = dict(dense["prediction"])
        dense_baseline["prediction"]["request_id"] = str(compound["compound_id"])
        conditions["direct_only"].append(direct_baseline)
        conditions["dense_only"].append(dense_baseline)
        conditions["claimwise_rule_decomposition"].extend((direct, dense))
    return conditions


def write_manifest(path: Path, compounds: Iterable[Mapping[str, Any]]) -> None:
    rows = []
    for compound in compounds:
        rows.append(
            {
                "compound_id": str(compound["compound_id"]),
                "sample_id": str(compound.get("sample_id", "")),
                "split": str(compound.get("split", "")),
                "language": str(compound.get("language", "en")),
                "query": str(compound.get("query", "")),
                "assets": dict(compound.get("assets", {})),
                "claims": [
                    {
                        "claim_id": f"{compound['compound_id']}:claim{index}",
                        "claim_index": index,
                        "role": str(claim.get("role", "")),
                        "canonical_intent": str(claim.get("canonical_intent", "")),
                        "query": str(claim.get("query", "")),
                        "supervision": dict(claim.get("supervision", {})),
                        "gold_request": claim.get("gold_request", {}),
                    }
                    for index, claim in enumerate(compound["claims"])
                ],
            }
        )
    write_jsonl(path, rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Expand CMGE compounds into executable conditions.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--count", type=int)
    parser.add_argument(
        "--asset-root",
        help="Rewrite any /benchmark/10M suffix to this server-local dataset root.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    compounds = read_jsonl(args.input)
    if args.count is not None:
        compounds = read_jsonl(args.input)[: args.count]
        conditions = build_conditions(compounds, args.asset_root)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, rows in conditions.items():
            write_jsonl(args.output_dir / name / "predictions.jsonl", rows)
        write_manifest(args.output_dir / "compound_manifest.jsonl", compounds)
        counts = {name: len(rows) for name, rows in conditions.items()}
        report = {
            "schema_version": "cmge.conditions.v1",
            "compound_count": min(args.count, len(compounds)),
            "condition_row_counts": counts,
            "claimwise_rows_per_compound": 2,
            "request_ids_are_gold_actions_with_rewritten_ids": True,
        }
        (args.output_dir / "conditions_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    conditions = build_conditions(compounds, args.asset_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in conditions.items():
        write_jsonl(args.output_dir / name / "predictions.jsonl", rows)
    write_manifest(args.output_dir / "compound_manifest.jsonl", compounds)
    report = {
        "schema_version": "cmge.conditions.v1",
        "compound_count": len(compounds),
        "condition_row_counts": {name: len(rows) for name, rows in conditions.items()},
        "claimwise_rows_per_compound": 2,
        "request_ids_are_gold_actions_with_rewritten_ids": True,
    }
    (args.output_dir / "conditions_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
