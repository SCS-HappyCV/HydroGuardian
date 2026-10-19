from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


OLD_DATA_ROOT = "/data/wcs10m"
CURRENT_DATA_ROOT = "/workspace/HydroGuardian/benchmark/10M"
LEVELS = ("L2", "L3")
LANGUAGES = ("en", "zh")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a fixed ERPO gate pilot on validation relation requests."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260820)
    parser.add_argument("--source-root", default=OLD_DATA_ROOT)
    parser.add_argument("--target-root", default=CURRENT_DATA_ROOT)
    return parser


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number} must contain an object")
            rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _map_paths(value: Any, source_root: str, target_root: str) -> Any:
    if isinstance(value, str):
        return value.replace(source_root, target_root)
    if isinstance(value, list):
        return [_map_paths(item, source_root, target_root) for item in value]
    if isinstance(value, dict):
        return {
            key: _map_paths(item, source_root, target_root)
            for key, item in value.items()
        }
    return value


def _parent_id(row: Mapping[str, Any]) -> str:
    provenance = row.get("provenance")
    if isinstance(provenance, Mapping) and provenance.get("parent_query_id"):
        return str(provenance["parent_query_id"])
    return str(row["query_id"]).rsplit(":", 2)[0]


def _add_evaluation_fields(row: Dict[str, Any]) -> None:
    row["id"] = str(row["query_id"])
    row["metadata"] = {
        "canonical_intent": str(row.get("canonical_intent", "")),
        "output_granularity": str(row.get("output_granularity", "")),
        "parent_query_id": _parent_id(row),
        "language": str(row.get("language", "")),
        "ambiguity_level": str(row.get("ambiguity_level", "")),
    }


def select_rows(rows: Sequence[Mapping[str, Any]], count: int, seed: int) -> List[Dict[str, Any]]:
    if count <= 0:
        raise ValueError("count must be positive")
    groups: Dict[tuple[str, str], List[Mapping[str, Any]]] = defaultdict(list)
    seen_parents: set[str] = set()
    eligible = sorted(
        (
            row
            for row in rows
            if row.get("split") == "val"
            and row.get("canonical_intent") == "relation_segmentation"
            and row.get("ambiguity_level") in LEVELS
            and row.get("language") in LANGUAGES
        ),
        key=lambda row: str(row.get("query_id", "")),
    )
    rng = random.Random(seed)
    rng.shuffle(eligible)
    for row in eligible:
        parent = _parent_id(row)
        if parent in seen_parents:
            continue
        seen_parents.add(parent)
        key = (str(row["ambiguity_level"]), str(row["language"]))
        groups[key].append(row)

    keys = [(level, language) for level in LEVELS for language in LANGUAGES]
    base, remainder = divmod(count, len(keys))
    quotas = {key: base + int(index < remainder) for index, key in enumerate(keys)}
    selected: List[Dict[str, Any]] = []
    for key in keys:
        if len(groups[key]) < quotas[key]:
            raise ValueError(f"Not enough unique requests for {key}: {len(groups[key])}")
        selected.extend(copy.deepcopy(groups[key][: quotas[key]]))
    selected.sort(key=lambda row: str(row["query_id"]))
    return selected


def _workflow_steps(row: Mapping[str, Any]) -> List[Dict[str, Any]]:
    request = row.get("gold_request")
    action = request.get("action") if isinstance(request, Mapping) else None
    steps = action.get("steps") if isinstance(action, Mapping) else None
    if not isinstance(steps, list) or len(steps) != 2:
        raise ValueError(f"{row.get('query_id')} is not a two-step relation workflow")
    return copy.deepcopy(steps)


def candidate_a_request(row: Mapping[str, Any]) -> Dict[str, Any]:
    request = copy.deepcopy(row["gold_request"])
    steps = _workflow_steps(row)
    segment = steps[0]
    relation = steps[1]
    segment_args = segment.get("arguments", {})
    segment["tool"] = "point_semantic_segmentation"
    segment["arguments"] = {
        "point_cloud_path": segment_args["point_cloud_path"],
        "return_probabilities": True,
        "target_class_ids": segment_args.get("target_class_ids", []),
    }
    relation_args = relation.get("arguments", {})
    relation_args["segmentation_result_path"] = (
        f"${{{segment['step_id']}.artifacts.point_labels}}"
    )
    relation["arguments"] = relation_args
    request["action"] = {"type": "workflow", "steps": steps}
    return request


def candidate_b_request(row: Mapping[str, Any]) -> Dict[str, Any]:
    steps = _workflow_steps(row)
    segment_args = steps[0]["arguments"]
    relation_args = steps[1]["arguments"]
    supervision = row.get("supervision", {})
    relation_rule = supervision.get("target_mask_rule", {})
    relation = str(relation_rule.get("type") or relation_args["operation"])
    return {
        "schema_version": "1.0",
        "request_id": str(row["query_id"]),
        "intent": "relation_segmentation",
        "action": {
            "type": "tool_call",
            "tool": "language_guided_point_segmentation",
            "verification": "required",
            "arguments": {
                "image_path": segment_args["image_path"],
                "point_cloud_path": segment_args["point_cloud_path"],
                "query": str(row["query"]),
                "target_class_ids": list(supervision.get("target_label_ids", [])),
                "reference_class_ids": list(supervision.get("reference_label_ids", [])),
                "relation": relation,
                "return_probabilities": True,
            },
        },
        "expected_output": {
            "type": "point_mask",
            "coordinate_space": "source_point_cloud",
        },
    }


def _condition_rows(
    rows: Sequence[Mapping[str, Any]],
    request_builder,
    source_root: str,
    target_root: str,
) -> List[Dict[str, Any]]:
    output = []
    for source in rows:
        row = _map_paths(copy.deepcopy(source), source_root, target_root)
        _add_evaluation_fields(row)
        row["gold_request"] = request_builder(row)
        output.append(row)
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = build_parser().parse_args()
    rows = select_rows(_read_jsonl(args.input), args.count, args.seed)
    original = [
        _map_paths(copy.deepcopy(row), args.source_root, args.target_root) for row in rows
    ]
    for row in original:
        _add_evaluation_fields(row)
    candidate_a = _condition_rows(
        rows, candidate_a_request, args.source_root, args.target_root
    )
    candidate_b = _condition_rows(
        rows, candidate_b_request, args.source_root, args.target_root
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "gold": args.output_dir / "gold_val_l2_l3_relation_50.jsonl",
        "candidate_a": args.output_dir / "candidate_a_point_geometry_50.jsonl",
        "candidate_b": args.output_dir / "candidate_b_language_direct_50.jsonl",
    }
    _write_jsonl(paths["gold"], original)
    _write_jsonl(paths["candidate_a"], candidate_a)
    _write_jsonl(paths["candidate_b"], candidate_b)
    manifest = {
        "schema_version": "erpo.gate_pilot.v1",
        "seed": args.seed,
        "count": len(rows),
        "split": "val",
        "task": "relation_segmentation",
        "levels": list(LEVELS),
        "languages": list(LANGUAGES),
        "selection": "unique parent_query_id, balanced by level and language",
        "candidate_a": "point_semantic_segmentation -> geometry_relation_analysis",
        "candidate_b": "language_guided_point_segmentation",
        "counts": {
            "level": dict(Counter(str(row["ambiguity_level"]) for row in rows)),
            "language": dict(Counter(str(row["language"]) for row in rows)),
            "relation": dict(
                Counter(str(row["supervision"]["target_mask_rule"]["type"]) for row in rows)
            ),
        },
        "files": {
            name: {"path": str(path), "sha256": _sha256(path)}
            for name, path in paths.items()
        },
    }
    manifest_path = args.output_dir / "pilot_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
