from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from hydro_remote_agent.backbones.qwen3_vl_planner import action_type, canonical_json


EVAL_MANIFEST_SCHEMA_VERSION = "vague_hydro.agent_eval_manifest.v1"
BucketKey = Tuple[str, str, str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} must contain an object")
            yield payload


def bucket_key(record: Mapping[str, Any]) -> BucketKey:
    return (
        str(record.get("language", "unknown")),
        str(record.get("ambiguity_level", "unknown")),
        action_type(record) or "unknown",
    )


def _stable_rank(record: Mapping[str, Any], seed: int) -> str:
    value = f"{seed}:{record.get('id', '')}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def select_stratified_unique(
    records: Sequence[Mapping[str, Any]],
    count: int,
    seed: int,
    group_field: str = "sample_id",
) -> List[Dict[str, Any]]:
    if count <= 0:
        raise ValueError("count must be positive")
    buckets: Dict[BucketKey, List[Dict[str, Any]]] = defaultdict(list)
    for raw_record in records:
        record = dict(raw_record)
        if not str(record.get(group_field, "")):
            raise ValueError(f"record {record.get('id')!r} is missing {group_field}")
        buckets[bucket_key(record)].append(record)
    if not buckets:
        raise ValueError("input contains no records")
    keys = sorted(buckets)
    if count % len(keys):
        raise ValueError(
            f"count {count} must be divisible by the {len(keys)} stratification buckets"
        )
    quota = count // len(keys)
    for values in buckets.values():
        values.sort(key=lambda item: _stable_rank(item, seed))

    selected: List[Dict[str, Any]] = []
    used_groups = set()
    bucket_counts: Counter[BucketKey] = Counter()
    for _ in range(quota):
        for key in keys:
            candidate = next(
                (
                    record
                    for record in buckets[key]
                    if str(record[group_field]) not in used_groups
                ),
                None,
            )
            if candidate is None:
                raise ValueError(
                    f"bucket {key} cannot satisfy quota={quota} with globally unique {group_field}"
                )
            selected.append(candidate)
            used_groups.add(str(candidate[group_field]))
            bucket_counts[key] += 1
    if len(selected) != count or len(used_groups) != count:
        raise AssertionError("stratified unique selection invariant failed")
    if set(bucket_counts.values()) != {quota}:
        raise AssertionError("bucket quota invariant failed")
    return selected


def _record_sets(records: Iterable[Mapping[str, Any]]) -> Dict[str, set[str]]:
    output = {"ids": set(), "sample_ids": set(), "images": set()}
    for record in records:
        output["ids"].add(str(record.get("id", "")))
        output["sample_ids"].add(str(record.get("sample_id", "")))
        images = record.get("images", [])
        if isinstance(images, list):
            output["images"].update(str(path) for path in images)
    output["ids"].discard("")
    output["sample_ids"].discard("")
    output["images"].discard("")
    return output


def build_eval_manifest(
    input_path: Path,
    training_path: Path,
    output_path: Path,
    report_path: Path,
    count: int = 240,
    seed: int = 20260731,
) -> Dict[str, Any]:
    selected = select_stratified_unique(
        list(iter_jsonl(input_path)),
        count=count,
        seed=seed,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(canonical_json(record) + "\n" for record in selected),
        encoding="utf-8",
    )
    selected_sets = _record_sets(selected)
    training_sets = _record_sets(iter_jsonl(training_path))
    overlaps = {
        key: sorted(selected_sets[key] & training_sets[key])
        for key in selected_sets
    }
    bucket_counts = Counter(bucket_key(record) for record in selected)
    report = {
        "schema_version": EVAL_MANIFEST_SCHEMA_VERSION,
        "status": "passed" if not any(overlaps.values()) else "failed",
        "seed": seed,
        "count": len(selected),
        "unique_sample_id_count": len(selected_sets["sample_ids"]),
        "unique_image_count": len(selected_sets["images"]),
        "bucket_counts": {
            "/".join(key): value for key, value in sorted(bucket_counts.items())
        },
        "overlap_counts": {key: len(value) for key, value in overlaps.items()},
        "overlap_examples": {key: value[:20] for key, value in overlaps.items()},
        "input_sha256": sha256_file(input_path),
        "training_sha256": sha256_file(training_path),
        "manifest_sha256": sha256_file(output_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if report["status"] != "passed":
        raise ValueError(f"evaluation manifest overlaps training data: {report['overlap_counts']}")
    return report
