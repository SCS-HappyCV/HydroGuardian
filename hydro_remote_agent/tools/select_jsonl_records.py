from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from hydro_remote_agent.evaluation.routing import extract_gold


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            records.append(value)
    return records


def _record_id(record: Dict[str, Any]) -> str:
    request_id = record.get("request_id") or record.get("id")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("Every record must contain a non-empty request_id or id")
    return request_id


def _action_type(record: Dict[str, Any]) -> Optional[str]:
    action_type = record.get("action_type")
    if isinstance(action_type, str):
        return action_type
    prediction = record.get("prediction")
    if isinstance(prediction, dict):
        action = prediction.get("action")
        if isinstance(action, dict) and isinstance(action.get("type"), str):
            return str(action["type"])
    if "messages" in record:
        _, request, _ = extract_gold(record)
        action = request.get("action")
        if isinstance(action, dict) and isinstance(action.get("type"), str):
            return str(action["type"])
    return None


def _selected_ids(paths: Iterable[Path]) -> Set[str]:
    selected: Set[str] = set()
    for path in paths:
        for record in _read_jsonl(path):
            request_id = _record_id(record)
            if request_id in selected:
                raise ValueError(f"Duplicate requested ID {request_id!r} in --ids-from inputs")
            selected.add(request_id)
    return selected


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select JSONL records without changing their order or content.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ids-from", action="append", default=[], type=Path)
    parser.add_argument("--action-type", action="append", default=[])
    parser.add_argument("--expected-input-sha256")
    parser.add_argument("--expected-count", type=int)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.expected_input_sha256:
        actual_sha256 = _sha256(args.input)
        if actual_sha256 != args.expected_input_sha256.lower():
            raise ValueError(
                f"Input SHA256 mismatch: expected {args.expected_input_sha256.lower()}, got {actual_sha256}"
            )

    records = _read_jsonl(args.input)
    ids = _selected_ids(args.ids_from)
    action_types = set(args.action_type)
    selected = [
        record
        for record in records
        if (not ids or _record_id(record) in ids)
        and (not action_types or _action_type(record) in action_types)
    ]
    if args.expected_count is not None and len(selected) != args.expected_count:
        raise ValueError(f"Expected {args.expected_count} records, selected {len(selected)}")

    selected_ids = [_record_id(record) for record in selected]
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("Selected records contain duplicate IDs")
    if ids and set(selected_ids) != ids:
        missing = sorted(ids - set(selected_ids))
        raise ValueError(f"Some requested IDs are absent from the input: {missing[:10]}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for record in selected:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"JSONL_SELECT_OK count={len(selected)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
