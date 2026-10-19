from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence, Set, Tuple

from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import ToolRegistry


SFT_SCHEMA_VERSION = "vague_hydro.sft.v1"
FREEZE_SCHEMA_VERSION = "vague_hydro.freeze.v1"


class SFTDataError(ValueError):
    """Raised when a frozen source or formatted SFT record is inconsistent."""


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SFTDataError(f"{path}:{line_number} is not valid JSON") from exc
            if not isinstance(payload, dict):
                raise SFTDataError(f"{path}:{line_number} must contain a JSON object")
            yield payload


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(canonical_json(record))
            handle.write("\n")
            count += 1
    return count


def compact_tool_catalog(registry: ToolRegistry) -> List[Dict[str, Any]]:
    return [
        tool.to_openai_tool()
        for tool in sorted(registry.tools, key=lambda item: item.name)
    ]


def build_system_prompt(
    ontology: Mapping[str, Any],
    action_schema_version: str = "1.0",
) -> str:
    planner_contract = {
        "agent": "VagueHydro Planner",
        "action_schema_version": action_schema_version,
        "allowed_action_types": [
            "direct_answer",
            "tool_call",
            "workflow",
            "clarification",
            "abstain",
        ],
        "class_names": ontology.get("class_names", {}),
        "supported_relations": ontology.get("supported_relations", []),
    }
    return (
        "You are the VagueHydro Planner. Read the user query and asset inventory, then return "
        "exactly one JSON AgentRequest and no prose or Markdown. The JSON must contain "
        "schema_version, request_id, intent, action, and expected_output. Use only the supplied "
        "tools and arguments. Preserve asset paths exactly. Use direct_answer only when the "
        "provided scene supervision supports the answer; request missing required assets with "
        "clarification; use abstain for unsupported capabilities. A workflow must list steps in "
        "dependency order and reference prior artifacts as ${step_id.artifacts.artifact_name}. "
        "Keep generated argument strings concise: each string must be at most 160 characters, "
        "and never repeat a word or phrase to fill space. Close the JSON object immediately "
        "after the required fields are complete. "
        "Contract: "
        + canonical_json(planner_contract)
    )


def load_source_manifest(path: Path) -> Dict[str, Dict[str, Any]]:
    output: Dict[str, Dict[str, Any]] = {}
    for record in iter_jsonl(path):
        sample_id = str(record.get("sample_id", ""))
        if not sample_id:
            raise SFTDataError("source manifest record is missing sample_id")
        if sample_id in output:
            raise SFTDataError(f"duplicate source manifest sample_id {sample_id!r}")
        output[sample_id] = record
    return output


def apply_path_maps(value: Any, path_maps: Sequence[Tuple[str, str]]) -> Any:
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        for source, target in path_maps:
            source_prefix = source.replace("\\", "/").rstrip("/")
            if normalized == source_prefix or normalized.startswith(source_prefix + "/"):
                suffix = normalized[len(source_prefix) :]
                return target.replace("\\", "/").rstrip("/") + suffix
        return value
    if isinstance(value, list):
        return [apply_path_maps(item, path_maps) for item in value]
    if isinstance(value, dict):
        return {
            key: apply_path_maps(child, path_maps)
            for key, child in value.items()
        }
    return value


def format_sft_record(
    record: Mapping[str, Any],
    manifest_record: Mapping[str, Any],
    system_prompt: str,
    tool_catalog: Sequence[Mapping[str, Any]],
    registry: ToolRegistry,
    path_maps: Sequence[Tuple[str, str]] = (),
) -> Dict[str, Any]:
    sample_id = str(record.get("sample_id", ""))
    if sample_id != str(manifest_record.get("sample_id", "")):
        raise SFTDataError(f"manifest mismatch for sample {sample_id!r}")
    split = str(record.get("split", ""))
    if split != str(manifest_record.get("split", "")):
        raise SFTDataError(f"split mismatch for sample {sample_id!r}")
    query_id = str(record.get("query_id", ""))
    query = str(record.get("query", "")).strip()
    if not query_id or not query:
        raise SFTDataError("generated record requires query_id and query")
    raw_gold_request = record.get("gold_request")
    if not isinstance(raw_gold_request, dict):
        raise SFTDataError(f"{query_id} gold_request must be an object")
    gold_request = apply_path_maps(raw_gold_request, path_maps)
    AgentRequest.from_dict(gold_request, registry)
    if str(gold_request.get("request_id", "")) != query_id:
        raise SFTDataError(f"{query_id} request_id does not match query_id")
    asset_paths = manifest_record.get("asset_paths")
    if not isinstance(asset_paths, dict):
        raise SFTDataError(f"{sample_id} manifest asset_paths must be an object")
    public_assets = {
        key: str(apply_path_maps(value, path_maps))
        for key, value in sorted(asset_paths.items())
        if key != "point_labels_path" and isinstance(value, str) and value
    }
    user_payload = {
        "request_id": query_id,
        "query": query,
        "language": str(record.get("language", "")),
        "assets": public_assets,
    }
    image_paths = [
        value
        for key, value in public_assets.items()
        if key.endswith("image_path")
    ]
    point_cloud_paths = [
        value
        for key, value in public_assets.items()
        if key.endswith("point_cloud_path")
    ]
    return {
        "schema_version": SFT_SCHEMA_VERSION,
        "id": query_id,
        "sample_id": sample_id,
        "split": split,
        "language": str(record.get("language", "")),
        "ambiguity_level": str(record.get("ambiguity_level", "")),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": canonical_json(user_payload)},
            {"role": "assistant", "content": canonical_json(gold_request)},
        ],
        "tools": [dict(tool) for tool in tool_catalog],
        "images": image_paths,
        "media": {
            "images": image_paths,
            "point_clouds": point_cloud_paths,
        },
        "metadata": {
            "canonical_intent": str(record.get("canonical_intent", "")),
            "output_granularity": str(record.get("output_granularity", "")),
            "parent_query_id": str(
                record.get("provenance", {}).get("parent_query_id", "")
                if isinstance(record.get("provenance"), dict)
                else ""
            ),
        },
    }


def format_sft_dataset(
    input_dir: Path,
    output_dir: Path,
    source_manifest_path: Path,
    ontology: Mapping[str, Any],
    registry: ToolRegistry,
    path_maps: Sequence[Tuple[str, str]] = (),
) -> Dict[str, Any]:
    manifest = load_source_manifest(source_manifest_path)
    system_prompt = build_system_prompt(ontology)
    tool_catalog = compact_tool_catalog(registry)
    counts: Counter = Counter()
    seen_ids: Set[str] = set()
    seen_samples_by_split: Dict[str, Set[str]] = {
        "train": set(),
        "val": set(),
        "test": set(),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "system_prompt.txt").write_text(system_prompt + "\n", encoding="utf-8")
    with (output_dir / "tool_catalog.json").open("w", encoding="utf-8") as handle:
        json.dump(tool_catalog, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    split_counts: Dict[str, int] = {}
    for split in ("train", "val", "test"):
        source_path = input_dir / f"vague_hydro_{split}.jsonl"
        if not source_path.exists():
            raise SFTDataError(f"missing generated split file {source_path}")

        def converted() -> Iterator[Dict[str, Any]]:
            for record in iter_jsonl(source_path):
                query_id = str(record.get("query_id", ""))
                sample_id = str(record.get("sample_id", ""))
                if query_id in seen_ids:
                    raise SFTDataError(f"duplicate query_id {query_id!r}")
                if sample_id not in manifest:
                    raise SFTDataError(f"{query_id} references unknown sample {sample_id!r}")
                formatted = format_sft_record(
                    record,
                    manifest[sample_id],
                    system_prompt,
                    tool_catalog,
                    registry,
                    path_maps,
                )
                seen_ids.add(query_id)
                seen_samples_by_split[split].add(sample_id)
                action = record["gold_request"]["action"]
                counts[f"split:{split}"] += 1
                counts[f"language:{record.get('language', '')}"] += 1
                counts[f"level:{record.get('ambiguity_level', '')}"] += 1
                counts[f"intent:{record.get('canonical_intent', '')}"] += 1
                counts[f"action:{action.get('type', '')}"] += 1
                yield formatted

        split_counts[split] = write_jsonl(output_dir / f"{split}_sft.jsonl", converted())

    overlaps = {
        "train_val": sorted(seen_samples_by_split["train"] & seen_samples_by_split["val"]),
        "train_test": sorted(seen_samples_by_split["train"] & seen_samples_by_split["test"]),
        "val_test": sorted(seen_samples_by_split["val"] & seen_samples_by_split["test"]),
    }
    if any(overlaps.values()):
        raise SFTDataError(f"sample leakage across splits: {overlaps}")
    output_hashes = {
        path.name: sha256_file(path)
        for path in sorted(output_dir.glob("*_sft.jsonl"))
    }
    report = {
        "schema_version": "vague_hydro.sft_report.v1",
        "status": "passed",
        "record_count": sum(split_counts.values()),
        "split_counts": split_counts,
        "language_counts": {
            key.split(":", 1)[1]: value
            for key, value in sorted(counts.items())
            if key.startswith("language:")
        },
        "ambiguity_level_counts": {
            key.split(":", 1)[1]: value
            for key, value in sorted(counts.items())
            if key.startswith("level:")
        },
        "intent_counts": {
            key.split(":", 1)[1]: value
            for key, value in sorted(counts.items())
            if key.startswith("intent:")
        },
        "action_type_counts": {
            key.split(":", 1)[1]: value
            for key, value in sorted(counts.items())
            if key.startswith("action:")
        },
        "sample_split_overlap_count": sum(len(value) for value in overlaps.values()),
        "system_prompt_sha256": sha256_payload(system_prompt),
        "tool_catalog_sha256": sha256_payload(tool_catalog),
        "output_sha256": output_hashes,
        "dataset_fingerprint": sha256_payload(output_hashes),
    }
    with (output_dir / "sft_report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return report


def freeze_generated_dataset(
    generated_dir: Path,
    source_manifest_path: Path,
    registry_path: Path,
    ontology_path: Path,
    extra_provenance_files: Sequence[Path] = (),
) -> Dict[str, Any]:
    required = [
        generated_dir / "vague_hydro_generated.jsonl",
        generated_dir / "vague_hydro_train.jsonl",
        generated_dir / "vague_hydro_val.jsonl",
        generated_dir / "vague_hydro_test.jsonl",
        generated_dir / "generation_report.json",
        source_manifest_path,
        registry_path,
        ontology_path,
    ]
    required.extend(extra_provenance_files)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SFTDataError(f"cannot freeze dataset; missing files: {missing}")
    with (generated_dir / "generation_report.json").open("r", encoding="utf-8") as handle:
        generation_report = json.load(handle)
    if generation_report.get("status") != "passed" or generation_report.get("failure_count") != 0:
        raise SFTDataError("generation report must be passed with zero failures")
    if (generated_dir / "generation_failures.jsonl").exists():
        raise SFTDataError("stale generation_failures.jsonl must be removed before freezing")

    logical_files: List[Tuple[str, Path]] = [
        ("generated/vague_hydro_generated.jsonl", generated_dir / "vague_hydro_generated.jsonl"),
        ("generated/vague_hydro_train.jsonl", generated_dir / "vague_hydro_train.jsonl"),
        ("generated/vague_hydro_val.jsonl", generated_dir / "vague_hydro_val.jsonl"),
        ("generated/vague_hydro_test.jsonl", generated_dir / "vague_hydro_test.jsonl"),
        ("generated/generation_report.json", generated_dir / "generation_report.json"),
        ("source/source_manifest.jsonl", source_manifest_path),
        ("schema/tool_registry.yaml", registry_path),
        ("schema/ontology.json", ontology_path),
    ]
    logical_files.extend(
        (f"provenance/{index:02d}-{path.name}", path)
        for index, path in enumerate(extra_provenance_files)
    )
    file_hashes = {
        logical_name: sha256_file(path)
        for logical_name, path in logical_files
    }
    split_counts = {
        split: sum(1 for _ in iter_jsonl(generated_dir / f"vague_hydro_{split}.jsonl"))
        for split in ("train", "val", "test")
    }
    total_count = sum(1 for _ in iter_jsonl(generated_dir / "vague_hydro_generated.jsonl"))
    if total_count != sum(split_counts.values()):
        raise SFTDataError("combined generated count does not equal split file counts")
    if total_count != int(generation_report.get("generated_count", -1)):
        raise SFTDataError("combined generated count does not match generation report")
    fingerprint = sha256_payload(file_hashes)
    return {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "status": "frozen",
        "record_count": total_count,
        "split_counts": split_counts,
        "source_generation_fingerprint": generation_report.get(
            "action_audit", {}
        ).get("dataset_fingerprint"),
        "file_sha256": file_hashes,
        "dataset_fingerprint": fingerprint,
    }
