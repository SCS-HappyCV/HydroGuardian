from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from hydro_remote_agent.schemas.agent_action import AgentActionError, AgentRequest
from hydro_remote_agent.schemas.tool_spec import ToolRegistry


MANIFEST_SCHEMA_VERSION = "vague_hydro.source_manifest.v1"
CANONICAL_SCHEMA_VERSION = "vague_hydro.canonical.v1"
VALID_SPLITS = {"train", "val", "test"}
VALID_TASK_TYPES = {"class", "attribute", "relation", "no_target"}


class VagueHydroAuditError(ValueError):
    """Raised when a VagueHydro record violates the frozen data contract."""


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def load_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise VagueHydroAuditError(f"{path}:{line_number} must contain a JSON object")
            records.append(payload)
    return records


def write_jsonl(path: str | Path, records: Iterable[Mapping[str, Any]]) -> int:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def load_split_assignments(path: str | Path) -> Dict[str, str]:
    split_path = Path(path)
    if split_path.suffix.lower() == ".jsonl":
        assignments: Dict[str, str] = {}
        for item in load_jsonl(split_path):
            sample_id = str(item.get("sample_id", "")).strip()
            split = str(item.get("split", "")).strip()
            if sample_id and split:
                assignments[sample_id] = split
        return assignments

    with split_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise VagueHydroAuditError("split map must be a JSON object")
    raw_assignments = payload.get("assignments", payload)
    if not isinstance(raw_assignments, dict):
        raise VagueHydroAuditError("split map assignments must be an object")
    assignments = {str(key): str(value) for key, value in raw_assignments.items()}
    invalid = sorted(set(assignments.values()) - VALID_SPLITS)
    if invalid:
        raise VagueHydroAuditError(f"split map contains invalid split values: {invalid}")
    return assignments


def parse_path_mappings(values: Sequence[str]) -> List[Tuple[str, str]]:
    mappings: List[Tuple[str, str]] = []
    for item in values:
        if "=" not in item:
            raise VagueHydroAuditError(f"invalid path mapping {item!r}; expected SRC=DST")
        source, destination = item.split("=", 1)
        source = source.strip().replace("\\", "/").rstrip("/")
        destination = destination.strip().replace("\\", "/").rstrip("/")
        if not source or not destination:
            raise VagueHydroAuditError(f"invalid path mapping {item!r}; expected SRC=DST")
        mappings.append((source, destination))
    return mappings


def _remap_path(value: str, mappings: Sequence[Tuple[str, str]]) -> str:
    normalized = str(value).replace("\\", "/")
    for source, destination in mappings:
        if normalized.startswith(source):
            return destination + normalized[len(source) :]
    return normalized


def audit_asset_paths(
    manifest_records: Sequence[Mapping[str, Any]],
    path_mappings: Sequence[Tuple[str, str]] = (),
    require_all: bool = False,
) -> Dict[str, Any]:
    checked = Counter()
    missing = Counter()
    missing_examples: Dict[str, List[str]] = {}
    unique_paths = set()
    for record in manifest_records:
        asset_paths = record.get("asset_paths")
        if not isinstance(asset_paths, dict):
            raise VagueHydroAuditError("manifest asset_paths must be an object")
        for field_name, raw_path in asset_paths.items():
            resolved = _remap_path(str(raw_path), path_mappings)
            dedup_key = (field_name, resolved)
            if dedup_key in unique_paths:
                continue
            unique_paths.add(dedup_key)
            checked[field_name] += 1
            if not Path(resolved).is_file():
                missing[field_name] += 1
                missing_examples.setdefault(field_name, [])
                if len(missing_examples[field_name]) < 5:
                    missing_examples[field_name].append(resolved)
    report = {
        "status": "passed" if not missing else "failed",
        "checked_counts": dict(sorted(checked.items())),
        "missing_counts": dict(sorted(missing.items())),
        "missing_examples": missing_examples,
    }
    if missing and require_all:
        raise VagueHydroAuditError(f"asset path audit failed: {report}")
    return report


def _target_ids(text_item: Mapping[str, Any]) -> List[int]:
    values = sorted({int(value) for value in text_item.get("target_label_ids", [])})
    if any(value < 1 or value > 15 for value in values):
        raise VagueHydroAuditError(f"target_label_ids out of range: {values}")
    return values


def _reference_ids(text_item: Mapping[str, Any]) -> List[int]:
    values = sorted({int(value) for value in text_item.get("reference_label_ids", [])})
    if any(value < 1 or value > 15 for value in values):
        raise VagueHydroAuditError(f"reference_label_ids out of range: {values}")
    return values


def _relation_rule(text_item: Mapping[str, Any]) -> Dict[str, Any]:
    rule = text_item.get("target_mask_rule")
    if not isinstance(rule, dict):
        raise VagueHydroAuditError(
            f"relation text {text_item.get('text_id')} is missing target_mask_rule"
        )
    relation_type = str(rule.get("type", "")).strip()
    if relation_type not in {"near", "above"}:
        raise VagueHydroAuditError(f"unsupported relation type {relation_type!r}")
    normalized: Dict[str, Any] = {
        "type": relation_type,
        "source_label": int(rule["source_label"]),
        "reference_label": int(rule["reference_label"]),
    }
    if relation_type == "near":
        normalized["distance_threshold_m"] = float(rule.get("distance_threshold_m", 3.0))
    else:
        normalized["z_margin_m"] = float(rule.get("z_margin_m", 0.2))
    return normalized


def _annotation_summary(texts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    task_counts: Counter[str] = Counter()
    positive_ids = set()
    negative_ids = set()
    relation_rules: List[Dict[str, Any]] = []
    for item in texts:
        task_type = str(item.get("task_type", ""))
        task_counts[task_type] += 1
        if task_type == "no_target" or bool(item.get("is_no_target", False)):
            negative_ids.update(_target_ids(item))
        else:
            positive_ids.update(_target_ids(item))
        if task_type == "relation":
            positive_ids.update(_reference_ids(item))
            relation_rules.append(_relation_rule(item))
    unique_rules = {
        _canonical_json(rule): rule
        for rule in relation_rules
    }
    return {
        "text_count": len(texts),
        "task_type_counts": dict(sorted(task_counts.items())),
        "annotation_supported_label_ids": sorted(positive_ids),
        "annotation_absent_label_ids": sorted(negative_ids - positive_ids),
        "relation_rules": [unique_rules[key] for key in sorted(unique_rules)],
    }


def build_source_manifest(
    source_records: Sequence[Mapping[str, Any]],
    split_assignments: Mapping[str, str],
) -> List[Dict[str, Any]]:
    manifest: List[Dict[str, Any]] = []
    seen = set()
    for source in source_records:
        sample_id = str(source.get("sample_id", "")).strip()
        if not sample_id:
            raise VagueHydroAuditError("source record is missing sample_id")
        if sample_id in seen:
            raise VagueHydroAuditError(f"duplicate source sample_id {sample_id!r}")
        seen.add(sample_id)
        if sample_id not in split_assignments:
            raise VagueHydroAuditError(f"sample_id {sample_id!r} is missing from split map")
        split = str(split_assignments[sample_id])
        if split not in VALID_SPLITS:
            raise VagueHydroAuditError(f"sample_id {sample_id!r} has invalid split {split!r}")
        texts = source.get("texts", [])
        if not isinstance(texts, list):
            raise VagueHydroAuditError(f"sample_id {sample_id!r} texts must be a list")
        asset_paths = {
            "image_path": str(source.get("ortho_image_path", "")),
            "point_cloud_path": str(source.get("point_cloud_path", "")),
            "point_labels_path": str(source.get("point_labels_path", "")),
        }
        if not all(asset_paths.values()):
            raise VagueHydroAuditError(f"sample_id {sample_id!r} has incomplete asset paths")
        manifest.append(
            {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "sample_id": sample_id,
                "patch_id": str(source.get("patch_id", "")),
                "region_id": str(source.get("region_id", "")),
                "split": split,
                "asset_paths": asset_paths,
                "annotation_summary": _annotation_summary(texts),
                "source_fingerprint": _sha256(source),
            }
        )
    missing_sources = sorted(set(split_assignments) - seen)
    if missing_sources:
        raise VagueHydroAuditError(
            f"split map has {len(missing_sources)} samples missing from source JSONL"
        )
    return manifest


def _expected_output(result_type: str, coordinate_space: str) -> Dict[str, str]:
    return {"type": result_type, "coordinate_space": coordinate_space}


def _agent_request(
    request_id: str,
    intent: str,
    action: Dict[str, Any],
    expected_output: Dict[str, str],
) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "intent": intent,
        "action": action,
        "expected_output": expected_output,
    }


def _label_phrase(text_item: Mapping[str, Any]) -> str:
    names = [str(value).strip() for value in text_item.get("target_label_names", []) if str(value).strip()]
    return ", ".join(names) if names else "the requested target"


def _query_id(source_id: str, variant: str) -> str:
    normalized_source = str(source_id).strip().replace("_", "-")
    normalized_variant = str(variant).strip().replace("_", "-")
    return f"q:{normalized_source}:{normalized_variant}"


def _attribute_terms(text_item: Mapping[str, Any]) -> List[str]:
    return list(
        dict.fromkeys(
            str(value).strip()
            for field in ("attributes", "attribute_phrases")
            for value in text_item.get(field, [])
            if str(value).strip()
        )
    )


def _direct_spec(text_item: Mapping[str, Any]) -> Tuple[str, str]:
    task_type = str(text_item["task_type"])
    target = _label_phrase(text_item)
    if task_type == "class":
        return "class_presence", f"Yes. {target} is present in the scene."
    if task_type == "attribute":
        attributes = ", ".join(_attribute_terms(text_item))
        detail = f" with attributes: {attributes}" if attributes else ""
        return "attribute_judgement", f"Yes. The requested {target} region is present{detail}."
    if task_type == "relation":
        rule = _relation_rule(text_item)
        references = ", ".join(
            str(value) for value in text_item.get("reference_label_names", [])
        ) or "the reference target"
        return (
            "relation_judgement",
            f"Yes. {target} satisfies the {rule['type']} relation with {references}.",
        )
    if task_type == "no_target":
        return "class_presence", f"No. {target} is not present in the scene."
    raise VagueHydroAuditError(f"unsupported task_type {task_type!r}")


def _direct_query(text_item: Mapping[str, Any]) -> str:
    task_type = str(text_item["task_type"])
    target = _label_phrase(text_item)
    if task_type in {"class", "no_target"}:
        return f"Is {target} present in this scene?"
    if task_type == "attribute":
        attributes = ", ".join(_attribute_terms(text_item))
        qualifier = f" matching these attributes: {attributes}" if attributes else ""
        return f"Is there {target} in this scene{qualifier}?"
    if task_type == "relation":
        rule = _relation_rule(text_item)
        references = ", ".join(
            str(value) for value in text_item.get("reference_label_names", [])
        ) or "the reference target"
        return f"Is {target} {rule['type']} {references} in this scene?"
    raise VagueHydroAuditError(f"unsupported task_type {task_type!r}")


def _dense_query(text_item: Mapping[str, Any]) -> str:
    task_type = str(text_item["task_type"])
    target = _label_phrase(text_item)
    if task_type == "class":
        return f"Segment every point belonging to {target} in this scene."
    if task_type == "attribute":
        attributes = ", ".join(_attribute_terms(text_item))
        qualifier = f" matching these attributes: {attributes}" if attributes else ""
        return f"Segment all {target} points{qualifier}."
    if task_type == "relation":
        rule = _relation_rule(text_item)
        references = ", ".join(
            str(value) for value in text_item.get("reference_label_names", [])
        ) or "the reference target"
        return f"Segment all {target} points that are {rule['type']} {references}."
    if task_type == "no_target":
        return f"Segment every {target} point in this scene, returning an empty result if absent."
    raise VagueHydroAuditError(f"unsupported task_type {task_type!r}")


def _dense_spec(
    text_item: Mapping[str, Any],
    asset_paths: Mapping[str, str],
    query: str,
) -> Tuple[str, Dict[str, Any]]:
    task_type = str(text_item["task_type"])
    target_ids = _target_ids(text_item)
    if task_type == "class":
        return (
            "class_segmentation",
            {
                "type": "tool_call",
                "tool": "multimodal_semantic_segmentation",
                "arguments": {
                    "image_path": asset_paths["image_path"],
                    "point_cloud_path": asset_paths["point_cloud_path"],
                    "target_class_ids": target_ids,
                    "return_probabilities": True,
                },
                "verification": "required",
            },
        )
    if task_type in {"attribute", "no_target"}:
        intent = "attribute_segmentation" if task_type == "attribute" else "class_segmentation"
        return (
            intent,
            {
                "type": "tool_call",
                "tool": "language_guided_point_segmentation",
                "arguments": {
                    "image_path": asset_paths["image_path"],
                    "point_cloud_path": asset_paths["point_cloud_path"],
                    "query": query,
                    "target_class_ids": target_ids,
                    "return_probabilities": True,
                },
                "verification": "required",
            },
        )
    if task_type == "relation":
        rule = _relation_rule(text_item)
        geometry_arguments: Dict[str, Any] = {
            "point_cloud_path": asset_paths["point_cloud_path"],
            "segmentation_result_path": "${segment_scene.artifacts.point_labels}",
            "operation": rule["type"],
            "target_class_id": int(rule["source_label"]),
            "reference_class_id": int(rule["reference_label"]),
        }
        if rule["type"] == "near":
            geometry_arguments["distance_threshold_m"] = float(rule["distance_threshold_m"])
        else:
            geometry_arguments["z_margin_m"] = float(rule["z_margin_m"])
        return (
            "relation_segmentation",
            {
                "type": "workflow",
                "steps": [
                    {
                        "step_id": "segment_scene",
                        "tool": "multimodal_semantic_segmentation",
                        "arguments": {
                            "image_path": asset_paths["image_path"],
                            "point_cloud_path": asset_paths["point_cloud_path"],
                            "target_class_ids": sorted(
                                set(_target_ids(text_item) + _reference_ids(text_item))
                            ),
                            "return_probabilities": True,
                        },
                        "depends_on": [],
                        "verification": "required",
                    },
                    {
                        "step_id": "analyze_relation",
                        "tool": "geometry_relation_analysis",
                        "arguments": geometry_arguments,
                        "depends_on": ["segment_scene"],
                        "verification": "skip",
                    },
                ],
            },
        )
    raise VagueHydroAuditError(f"unsupported task_type {task_type!r}")


def _supervision(text_item: Mapping[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "source_task_type": str(text_item["task_type"]),
        "target_label_ids": _target_ids(text_item),
        "target_label_names": list(text_item.get("target_label_names", [])),
        "is_no_target": bool(text_item.get("is_no_target", False)),
    }
    if text_item.get("attributes") is not None:
        payload["attributes"] = list(text_item.get("attributes", []))
    if text_item.get("attribute_phrases") is not None:
        payload["attribute_phrases"] = list(text_item.get("attribute_phrases", []))
    if text_item.get("reference_label_ids") is not None:
        payload["reference_label_ids"] = _reference_ids(text_item)
        payload["reference_label_names"] = list(text_item.get("reference_label_names", []))
    if text_item.get("target_mask_rule") is not None:
        payload["target_mask_rule"] = _relation_rule(text_item)
    return payload


def _canonical_record(
    query_id: str,
    sample_id: str,
    split: str,
    query: str,
    intent: str,
    output_granularity: str,
    gold_request: Dict[str, Any],
    supervision: Dict[str, Any],
    source_text_id: str,
    derivation: str,
    source_query: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "query_id": query_id,
        "sample_id": sample_id,
        "split": split,
        "language": "en",
        "ambiguity_level": "source" if derivation == "source_direct" else "L0",
        "query": query,
        "canonical_intent": intent,
        "output_granularity": output_granularity,
        "gold_request": gold_request,
        "supervision": supervision,
        "provenance": {
            "source_text_id": source_text_id,
            "derivation": derivation,
            "generator": "deterministic_v1",
            **({"source_query": source_query} if source_query else {}),
        },
    }


def build_canonical_records(
    source_records: Sequence[Mapping[str, Any]],
    manifest_records: Sequence[Mapping[str, Any]],
    include_dense_variants: bool = True,
    include_full_scene_tasks: bool = True,
) -> List[Dict[str, Any]]:
    manifest_by_id = {str(item["sample_id"]): item for item in manifest_records}
    output: List[Dict[str, Any]] = []
    for source in source_records:
        sample_id = str(source["sample_id"])
        manifest = manifest_by_id[sample_id]
        split = str(manifest["split"])
        asset_paths = dict(manifest["asset_paths"])
        texts = source.get("texts", [])
        for text_item in texts:
            task_type = str(text_item.get("task_type", ""))
            if task_type not in VALID_TASK_TYPES:
                raise VagueHydroAuditError(f"unsupported source task type {task_type!r}")
            source_text_id = str(text_item["text_id"])
            source_query = str(text_item["text"]).strip()
            direct_intent, direct_answer = _direct_spec(text_item)
            direct_id = _query_id(source_text_id, "direct")
            direct_request = _agent_request(
                direct_id,
                direct_intent,
                {"type": "direct_answer", "answer": direct_answer},
                _expected_output("text", "none"),
            )
            output.append(
                _canonical_record(
                    query_id=direct_id,
                    sample_id=sample_id,
                    split=split,
                    query=_direct_query(text_item),
                    intent=direct_intent,
                    output_granularity="text",
                    gold_request=direct_request,
                    supervision=_supervision(text_item),
                    source_text_id=source_text_id,
                    derivation="normalized_direct",
                    source_query=source_query,
                )
            )

            if include_dense_variants:
                dense_query = _dense_query(text_item)
                dense_intent, dense_action = _dense_spec(text_item, asset_paths, dense_query)
                dense_id = _query_id(source_text_id, "dense")
                dense_request = _agent_request(
                    dense_id,
                    dense_intent,
                    dense_action,
                    _expected_output("point_mask", "source_point_cloud"),
                )
                output.append(
                    _canonical_record(
                        query_id=dense_id,
                        sample_id=sample_id,
                        split=split,
                        query=dense_query,
                        intent=dense_intent,
                        output_granularity="point_mask",
                        gold_request=dense_request,
                        supervision=_supervision(text_item),
                        source_text_id=source_text_id,
                        derivation="derived_dense",
                        source_query=source_query,
                    )
                )

        if include_full_scene_tasks:
            query_id = _query_id(sample_id, "full_scene")
            intent = "full_scene_segmentation"
            query = "Produce a complete 15-class point-level semantic map for this scene."
            request = _agent_request(
                query_id,
                intent,
                {
                    "type": "tool_call",
                    "tool": "multimodal_semantic_segmentation",
                    "arguments": {
                        "image_path": asset_paths["image_path"],
                        "point_cloud_path": asset_paths["point_cloud_path"],
                        "return_probabilities": True,
                    },
                    "verification": "required",
                },
                _expected_output("point_labels", "source_point_cloud"),
            )
            output.append(
                _canonical_record(
                    query_id=query_id,
                    sample_id=sample_id,
                    split=split,
                    query=query,
                    intent=intent,
                    output_granularity="point_labels",
                    gold_request=request,
                    supervision={
                        "source_task_type": "full_scene",
                        "target_label_ids": [],
                        "target_label_names": [],
                        "is_no_target": False,
                    },
                    source_text_id="",
                    derivation="derived_full_scene",
                )
            )
    return output


def _validate_canonical_shape(record: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "query_id",
        "sample_id",
        "split",
        "language",
        "ambiguity_level",
        "query",
        "canonical_intent",
        "output_granularity",
        "gold_request",
        "supervision",
        "provenance",
    }
    missing = sorted(required - set(record))
    if missing:
        raise VagueHydroAuditError(f"canonical record is missing fields: {missing}")
    if record["schema_version"] != CANONICAL_SCHEMA_VERSION:
        raise VagueHydroAuditError("unsupported canonical schema_version")
    if record["split"] not in VALID_SPLITS:
        raise VagueHydroAuditError(f"invalid split {record['split']!r}")
    if not str(record["query"]).strip():
        raise VagueHydroAuditError("query cannot be empty")
    if not isinstance(record["supervision"], dict) or not isinstance(record["provenance"], dict):
        raise VagueHydroAuditError("supervision and provenance must be objects")


def audit_dataset(
    manifest_records: Sequence[Mapping[str, Any]],
    canonical_records: Sequence[Mapping[str, Any]],
    registry: ToolRegistry,
) -> Dict[str, Any]:
    manifest_by_id: Dict[str, Mapping[str, Any]] = {}
    manifest_split_counts: Counter[str] = Counter()
    for record in manifest_records:
        sample_id = str(record.get("sample_id", ""))
        if not sample_id or sample_id in manifest_by_id:
            raise VagueHydroAuditError(f"invalid or duplicate manifest sample_id {sample_id!r}")
        if record.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            raise VagueHydroAuditError(f"invalid manifest schema for {sample_id}")
        split = str(record.get("split", ""))
        if split not in VALID_SPLITS:
            raise VagueHydroAuditError(f"invalid manifest split {split!r}")
        manifest_by_id[sample_id] = record
        manifest_split_counts[split] += 1

    query_ids = set()
    query_split_counts: Counter[str] = Counter()
    intent_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    derivation_counts: Counter[str] = Counter()
    no_target_counts: Counter[str] = Counter()
    failures: List[Dict[str, str]] = []
    normalized_query_splits: Dict[str, set[str]] = {}
    normalized_query_examples: Dict[str, str] = {}

    for index, record in enumerate(canonical_records):
        try:
            _validate_canonical_shape(record)
            query_id = str(record["query_id"])
            if query_id in query_ids:
                raise VagueHydroAuditError(f"duplicate query_id {query_id!r}")
            query_ids.add(query_id)
            sample_id = str(record["sample_id"])
            if sample_id not in manifest_by_id:
                raise VagueHydroAuditError(f"query references unknown sample_id {sample_id!r}")
            split = str(record["split"])
            if split != manifest_by_id[sample_id]["split"]:
                raise VagueHydroAuditError(
                    f"query split {split!r} disagrees with manifest split for {sample_id}"
                )
            request = AgentRequest.from_dict(record["gold_request"], registry)
            if request.request_id != query_id:
                raise VagueHydroAuditError("gold_request.request_id must equal query_id")
            if request.intent != record["canonical_intent"]:
                raise VagueHydroAuditError("gold_request.intent must equal canonical_intent")
            query_split_counts[split] += 1
            intent_counts[request.intent] += 1
            action_counts[request.action.type] += 1
            derivation_counts[str(record["provenance"].get("derivation", ""))] += 1
            no_target_counts[str(bool(record["supervision"].get("is_no_target", False))).lower()] += 1
            normalized_query = re.sub(r"\s+", " ", str(record["query"]).strip().lower())
            normalized_query_splits.setdefault(normalized_query, set()).add(split)
            normalized_query_examples.setdefault(normalized_query, str(record["query"]))
        except (AgentActionError, KeyError, TypeError, ValueError) as exc:
            failures.append(
                {
                    "index": str(index),
                    "query_id": str(record.get("query_id", "")),
                    "error": str(exc),
                }
            )

    if failures:
        preview = failures[:5]
        raise VagueHydroAuditError(
            f"{len(failures)} canonical records failed audit; first failures: {preview}"
        )

    fingerprint_payload = {
        "manifest": [_sha256(item) for item in manifest_records],
        "canonical": [_sha256(item) for item in canonical_records],
    }
    cross_split_collisions = [
        {
            "query": normalized_query_examples[query],
            "splits": sorted(splits),
        }
        for query, splits in normalized_query_splits.items()
        if len(splits) > 1
    ]
    cross_split_collisions.sort(key=lambda item: item["query"])
    return {
        "schema_version": "vague_hydro.audit.v1",
        "status": "passed",
        "manifest_count": len(manifest_records),
        "canonical_count": len(canonical_records),
        "manifest_split_counts": dict(sorted(manifest_split_counts.items())),
        "query_split_counts": dict(sorted(query_split_counts.items())),
        "intent_counts": dict(sorted(intent_counts.items())),
        "action_type_counts": dict(sorted(action_counts.items())),
        "derivation_counts": dict(sorted(derivation_counts.items())),
        "no_target_counts": dict(sorted(no_target_counts.items())),
        "cross_split_exact_query_collision_count": len(cross_split_collisions),
        "cross_split_exact_query_collision_examples": cross_split_collisions[:20],
        "dataset_fingerprint": _sha256(fingerprint_payload),
        "failure_count": 0,
    }
