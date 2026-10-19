from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from hydro_remote_agent.backbones.qwen3_vl_planner import action_type, canonical_json


def stable_rank(record_id: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{record_id}".encode("utf-8")).hexdigest()


def _stratum(record: Mapping[str, Any]) -> Tuple[str, str, str]:
    return (
        action_type(record),
        str(record.get("language", "unknown")),
        str(record.get("ambiguity_level", "unknown")),
    )


def _parent_id(record: Mapping[str, Any]) -> str:
    metadata = record.get("metadata")
    if isinstance(metadata, Mapping) and metadata.get("parent_query_id"):
        return str(metadata["parent_query_id"])
    return str(record.get("id", ""))


def _allocate(total: int, keys: Sequence[Tuple[str, str, str]]) -> Dict[Tuple[str, str, str], int]:
    base, remainder = divmod(total, len(keys))
    return {key: base + int(index < remainder) for index, key in enumerate(keys)}


def select_curriculum(
    records: Sequence[Mapping[str, Any]],
    action_quotas: Mapping[str, int],
    seed: int,
    max_records_per_tile: int,
    max_parent_variants: Mapping[str, int],
) -> List[Dict[str, Any]]:
    candidates = [dict(record) for record in records]
    candidates.sort(key=lambda item: stable_rank(str(item.get("id", "")), seed))
    by_stratum: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for record in candidates:
        by_stratum[_stratum(record)].append(record)

    stratum_quotas: Dict[Tuple[str, str, str], int] = {}
    for action, quota in action_quotas.items():
        keys = sorted(key for key in by_stratum if key[0] == action)
        if not keys:
            raise ValueError(f"no records available for action {action!r}")
        stratum_quotas.update(_allocate(int(quota), keys))

    selected: List[Dict[str, Any]] = []
    selected_ids = set()
    tile_counts: Counter = Counter()
    parent_counts: Counter = Counter()
    stratum_counts: Counter = Counter()

    def accept(record: Dict[str, Any], enforce_tile: bool, enforce_parent: bool) -> bool:
        record_id = str(record.get("id", ""))
        action, _, _ = _stratum(record)
        key = _stratum(record)
        tile = str(record.get("sample_id", ""))
        parent = _parent_id(record)
        if record_id in selected_ids or stratum_counts[key] >= stratum_quotas.get(key, 0):
            return False
        if enforce_tile and tile_counts[tile] >= max_records_per_tile:
            return False
        if enforce_parent and parent_counts[(action, parent)] >= int(max_parent_variants[action]):
            return False
        selected.append(record)
        selected_ids.add(record_id)
        tile_counts[tile] += 1
        parent_counts[(action, parent)] += 1
        stratum_counts[key] += 1
        return True

    for enforce_tile, enforce_parent in ((True, True), (False, True), (False, False)):
        for record in candidates:
            accept(record, enforce_tile=enforce_tile, enforce_parent=enforce_parent)

    missing = {
        key: quota - stratum_counts[key]
        for key, quota in stratum_quotas.items()
        if stratum_counts[key] != quota
    }
    if missing:
        raise ValueError(f"curriculum quotas cannot be satisfied: {missing}")
    selected.sort(key=lambda item: stable_rank(str(item["id"]), seed + 1))
    return selected


def curriculum_report(
    source_records: Sequence[Mapping[str, Any]],
    selected: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> Dict[str, Any]:
    counts: Counter = Counter()
    for record in selected:
        action, language, level = _stratum(record)
        counts[f"action:{action}"] += 1
        counts[f"language:{language}"] += 1
        counts[f"level:{level}"] += 1
        counts[f"stratum:{action}/{language}/{level}"] += 1
    ids = [str(record["id"]) for record in selected]
    return {
        "schema_version": "vague_hydro.curriculum.v1",
        "status": "passed",
        "source_count": len(source_records),
        "selected_count": len(selected),
        "unique_tile_count": len({str(record.get("sample_id", "")) for record in selected}),
        "unique_parent_count": len({_parent_id(record) for record in selected}),
        "action_counts": {key.split(":", 1)[1]: value for key, value in sorted(counts.items()) if key.startswith("action:")},
        "language_counts": {key.split(":", 1)[1]: value for key, value in sorted(counts.items()) if key.startswith("language:")},
        "ambiguity_level_counts": {key.split(":", 1)[1]: value for key, value in sorted(counts.items()) if key.startswith("level:")},
        "stratum_counts": {key.split(":", 1)[1]: value for key, value in sorted(counts.items()) if key.startswith("stratum:")},
        "config": dict(config),
        "dataset_fingerprint": hashlib.sha256(canonical_json(ids).encode("utf-8")).hexdigest(),
    }


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(canonical_json(record) + "\n")

