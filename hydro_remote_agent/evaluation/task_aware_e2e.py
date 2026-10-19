from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from hydro_remote_agent.evaluation.language_segmentation import binary_mask_metrics
from hydro_remote_agent.evaluation.routing import (
    canonical_json,
    extract_gold,
    iter_jsonl,
    parse_json_response,
    sha256_file,
)
from hydro_remote_agent.evaluation.segmentation import (
    confusion_matrix_1based,
    segmentation_metrics,
)


TASK_AWARE_SCHEMA_VERSION = "vague_hydro.task_aware_e2e.v1"
TASK_TYPES = ("class", "attribute", "relation", "no_target", "full_scene")


def load_annotation_index(path: Path) -> Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]]:
    index: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    for _, record in iter_jsonl(path):
        for text_item in record.get("texts", []):
            if not isinstance(text_item, dict) or not text_item.get("text_id"):
                continue
            text_id = str(text_item["text_id"])
            if text_id in index:
                raise ValueError(f"Duplicate annotation text_id {text_id!r}")
            index[text_id] = (dict(record), dict(text_item))
    return index


def annotation_id(record: Mapping[str, Any]) -> Optional[str]:
    metadata = record.get("metadata")
    parent = metadata.get("parent_query_id") if isinstance(metadata, Mapping) else None
    if not isinstance(parent, str) or not parent:
        return None
    value = parent[2:] if parent.startswith("q:") else parent
    value = value.split(":", 1)[0].replace("-", "_")
    return value


def task_type(record: Mapping[str, Any], gold_request: Mapping[str, Any]) -> str:
    request_id = str(record.get("id", ""))
    for name, marker in (
        ("no_target", "no-target"),
        ("relation", "relation"),
        ("attribute", "attribute"),
        ("class", "class"),
        ("full_scene", "full-scene"),
    ):
        if marker in request_id:
            return name
    intent = str(gold_request.get("intent", ""))
    if intent.startswith("full_scene"):
        return "full_scene"
    raise ValueError(f"Cannot infer task type for {request_id!r}")


def _assets(record: Mapping[str, Any]) -> Dict[str, Any]:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return {}
    for message in messages:
        if not isinstance(message, Mapping) or message.get("role") != "user":
            continue
        try:
            payload = json.loads(str(message.get("content", "")))
        except json.JSONDecodeError:
            continue
        assets = payload.get("assets") if isinstance(payload, Mapping) else None
        return dict(assets) if isinstance(assets, Mapping) else {}
    return {}


def _resolve_point_path(record: Mapping[str, Any], data_root: Optional[Path]) -> Path:
    if data_root is not None:
        sample_id = str(record["sample_id"])
        region_id, patch_id = sample_id.split("_", 1)
        return data_root / region_id / "velodyne" / f"{patch_id}.txt"
    point_path = _assets(record).get("point_cloud_path")
    if not isinstance(point_path, str):
        raise ValueError(f"Record {record.get('id')} has no point_cloud_path")
    return Path(point_path)


def _load_xyz_labels(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    points = np.loadtxt(path, dtype=np.float32)
    if points.ndim == 1:
        points = points.reshape(1, -1)
    if points.shape[1] < 7:
        raise ValueError(f"Point cloud {path} must contain XYZRGB+label")
    return points[:, :3], points[:, 6].astype(np.int64)


def _target_mask(
    xyz: np.ndarray,
    labels: np.ndarray,
    text_item: Mapping[str, Any],
) -> np.ndarray:
    rule = text_item.get("target_mask_rule")
    if isinstance(rule, Mapping):
        import torch
        from wcs_unified.dataset import build_rule_target_mask

        return build_rule_target_mask(
            torch.from_numpy(xyz),
            torch.from_numpy(labels),
            dict(rule),
        ).cpu().numpy().astype(np.bool_)
    target = np.zeros(len(labels), dtype=np.bool_)
    if not bool(text_item.get("is_no_target", False)):
        for class_id in text_item.get("target_label_ids", []):
            target |= labels == int(class_id)
    return target


def _execution_artifacts(run: Mapping[str, Any]) -> Dict[str, List[str]]:
    output: Dict[str, List[str]] = defaultdict(list)
    execution = run.get("execution")
    result = execution.get("result") if isinstance(execution, Mapping) else None
    if not isinstance(result, Mapping):
        return output
    artifact_groups = [result.get("terminal_artifacts")]
    workflow = result.get("workflow_result")
    if isinstance(workflow, Mapping):
        for step in workflow.get("steps", []):
            step_result = step.get("result") if isinstance(step, Mapping) else None
            if isinstance(step_result, Mapping):
                artifact_groups.append(step_result.get("artifacts"))
    for artifacts in artifact_groups:
        if not isinstance(artifacts, Mapping):
            continue
        for name, path in artifacts.items():
            if isinstance(path, str) and path not in output[str(name)]:
                output[str(name)].append(path)
    return output


def _load_npz_array(artifacts: Mapping[str, Sequence[str]], name: str) -> Optional[np.ndarray]:
    for value in artifacts.get(name, ()):
        path = Path(value)
        if not path.is_file():
            continue
        with np.load(path, allow_pickle=False) as payload:
            key = name if name in payload.files else payload.files[0]
            return np.asarray(payload[key])
    return None


def _normalized_text(value: Any) -> str:
    return re.sub(r"[\W_]+", "", str(value).casefold(), flags=re.UNICODE)


def _polarity(value: Any) -> Optional[str]:
    text = str(value).strip().casefold()
    if re.search(r"\b(no|not present|absent|does not|isn't|cannot)\b", text):
        return "no"
    if re.search(r"\b(yes|present|there is|visible)\b", text):
        return "yes"
    compact = re.sub(r"\s+", "", text)
    if any(marker in compact for marker in ("不存在", "没有", "未发现", "不可见")):
        return "no"
    if any(marker in compact for marker in ("存在", "有", "可见", "是的")):
        return "yes"
    return None


def _direct_score(gold_request: Mapping[str, Any], prediction: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    gold_action = gold_request.get("action")
    predicted_action = prediction.get("action") if isinstance(prediction, Mapping) else None
    gold_answer = gold_action.get("answer") if isinstance(gold_action, Mapping) else None
    predicted_answer = predicted_action.get("answer") if isinstance(predicted_action, Mapping) else None
    exact = bool(
        predicted_answer is not None
        and _normalized_text(gold_answer) == _normalized_text(predicted_answer)
    )
    gold_polarity = _polarity(gold_answer)
    predicted_polarity = _polarity(predicted_answer)
    semantic = exact or bool(gold_polarity and gold_polarity == predicted_polarity)
    return {
        "output_available": predicted_answer is not None,
        "task_score": float(semantic),
        "metrics": {
            "answer_exact": exact,
            "answer_semantic_correct": semantic,
            "gold_polarity": gold_polarity,
            "predicted_polarity": predicted_polarity,
        },
    }


def _route_exact(gold_request: Mapping[str, Any], run: Mapping[str, Any]) -> bool:
    try:
        prediction = parse_json_response(run.get("prediction"))
    except Exception:
        return False
    return canonical_json(gold_request) == canonical_json(prediction)


def score_request(
    record: Mapping[str, Any],
    run: Mapping[str, Any],
    annotations: Mapping[str, Tuple[Dict[str, Any], Dict[str, Any]]],
    data_root: Optional[Path],
    scene_data: Optional[Tuple[np.ndarray, np.ndarray]] = None,
) -> Dict[str, Any]:
    request_id, gold_request, metadata = extract_gold(record)
    gold_action = gold_request.get("action")
    gold_action_type = str(gold_action.get("type", "")) if isinstance(gold_action, Mapping) else ""
    current_task_type = task_type(record, gold_request)
    execution = run.get("execution")
    execution_succeeded = bool(
        isinstance(execution, Mapping) and execution.get("status") == "succeeded"
    )
    try:
        prediction = parse_json_response(run.get("prediction"))
    except Exception:
        prediction = None
    base = {
        "id": request_id,
        "sample_id": str(record.get("sample_id", "")),
        "condition": str(run.get("condition", "")),
        "language": metadata.get("language") or str(record.get("language", "unknown")),
        "ambiguity_level": metadata.get("ambiguity_level") or str(record.get("ambiguity_level", "unknown")),
        "gold_action_type": gold_action_type,
        "task_type": current_task_type,
        "execution_succeeded": execution_succeeded,
        "routing_exact": _route_exact(gold_request, run),
        "score_status": "scored",
    }

    if gold_action_type == "direct_answer":
        score = _direct_score(gold_request, prediction)
        return {**base, "score_kind": "direct_answer", **score}

    if scene_data is None:
        point_path = _resolve_point_path(record, data_root)
        xyz, labels = _load_xyz_labels(point_path)
    else:
        xyz, labels = scene_data
    artifacts = _execution_artifacts(run)
    if current_task_type == "full_scene":
        predicted_labels = _load_npz_array(artifacts, "point_labels")
        available = predicted_labels is not None and predicted_labels.reshape(-1).shape == labels.shape
        if available:
            confusion = confusion_matrix_1based(labels, predicted_labels.reshape(-1))
            metrics = segmentation_metrics(confusion)
            score = float(metrics["mean_iou"] or 0.0)
        else:
            metrics = {
                "mean_iou": 0.0,
                "overall_accuracy": 0.0,
                "evaluated_points": int(np.count_nonzero((labels >= 1) & (labels <= 15))),
                "evaluated_class_count": int(len(np.unique(labels[(labels >= 1) & (labels <= 15)]))),
            }
            score = 0.0
        return {
            **base,
            "score_kind": "full_scene_segmentation",
            "output_available": available,
            "task_score": score,
            "metrics": metrics,
            "score_status": "scored" if available else "missing_required_output",
        }

    text_id = annotation_id(record)
    if text_id not in annotations:
        raise ValueError(f"No annotation found for {request_id!r}: expected {text_id!r}")
    _, text_item = annotations[text_id]
    target = _target_mask(xyz, labels, text_item)
    prediction_mask = None
    for artifact_name in (
        ("relation_mask", "target_mask")
        if current_task_type == "relation"
        else ("target_mask",)
    ):
        prediction_mask = _load_npz_array(artifacts, artifact_name)
        if prediction_mask is not None:
            break
    if prediction_mask is None and current_task_type != "relation":
        predicted_labels = _load_npz_array(artifacts, "point_labels")
        if predicted_labels is not None and predicted_labels.reshape(-1).shape == labels.shape:
            prediction_mask = np.zeros(len(labels), dtype=np.bool_)
            for class_id in text_item.get("target_label_ids", []):
                prediction_mask |= predicted_labels.reshape(-1) == int(class_id)
    available = prediction_mask is not None and prediction_mask.reshape(-1).shape == target.shape
    if available:
        metrics = binary_mask_metrics(target, prediction_mask.reshape(-1))
    else:
        target_count = int(np.count_nonzero(target))
        metrics = {
            "intersection": 0,
            "union": target_count,
            "target_points": target_count,
            "predicted_points": 0,
            "iou": 0.0,
            "dice": 0.0,
        }
    metrics["is_no_target"] = bool(text_item.get("is_no_target", False))
    metrics["predicted_no_target"] = bool(metrics["predicted_points"] == 0) if available else None
    return {
        **base,
        "score_kind": "binary_mask",
        "output_available": available,
        "task_score": float(metrics["iou"]),
        "metrics": metrics,
        "score_status": "scored" if available else "missing_required_output",
    }


def _mean(values: Sequence[float]) -> Optional[float]:
    return float(np.mean(values)) if values else None


def aggregate_rows(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    direct = [row for row in rows if row.get("score_kind") == "direct_answer"]
    masks = [row for row in rows if row.get("score_kind") == "binary_mask"]
    full_scene = [row for row in rows if row.get("score_kind") == "full_scene_segmentation"]
    available_masks = [row for row in masks if row.get("output_available")]
    intersections = sum(int(row["metrics"]["intersection"]) for row in masks)
    unions = sum(int(row["metrics"]["union"]) for row in masks)
    target_points = sum(int(row["metrics"]["target_points"]) for row in masks)
    predicted_points = sum(int(row["metrics"]["predicted_points"]) for row in masks)
    no_target_scored = [
        row for row in available_masks if row["metrics"].get("predicted_no_target") is not None
    ]
    tp = sum(
        bool(row["metrics"].get("is_no_target"))
        and bool(row["metrics"].get("predicted_no_target"))
        for row in no_target_scored
    )
    fp = sum(
        not bool(row["metrics"].get("is_no_target"))
        and bool(row["metrics"].get("predicted_no_target"))
        for row in no_target_scored
    )
    fn = sum(
        bool(row["metrics"].get("is_no_target"))
        and not bool(row["metrics"].get("predicted_no_target"))
        for row in no_target_scored
    )
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {
        "request_count": len(rows),
        "execution_success_rate": _mean([float(bool(row.get("execution_succeeded"))) for row in rows]),
        "routing_exact_rate": _mean([float(bool(row.get("routing_exact"))) for row in rows]),
        "output_availability_rate": _mean([float(bool(row.get("output_available"))) for row in rows]),
        "mean_per_request_task_score": _mean([float(row.get("task_score", 0.0)) for row in rows]),
        "score_definition": "direct semantic accuracy, binary-mask IoU, or full-scene mIoU; missing required outputs score zero",
        "direct_answer": {
            "count": len(direct),
            "accuracy": _mean([float(row["metrics"]["answer_semantic_correct"]) for row in direct]),
            "exact_accuracy": _mean([float(row["metrics"]["answer_exact"]) for row in direct]),
        },
        "binary_mask": {
            "count": len(masks),
            "available_count": len(available_masks),
            "macro_iou": _mean([float(row["metrics"]["iou"]) for row in masks]),
            "macro_dice": _mean([float(row["metrics"]["dice"]) for row in masks]),
            "micro_iou": 1.0 if unions == 0 else intersections / unions,
            "micro_dice": (
                1.0
                if target_points + predicted_points == 0
                else 2 * intersections / (target_points + predicted_points)
            ),
            "no_target_scored_count": len(no_target_scored),
            "no_target_precision": precision,
            "no_target_recall": recall,
            "no_target_f1": f1,
        },
        "full_scene": {
            "count": len(full_scene),
            "available_count": sum(bool(row.get("output_available")) for row in full_scene),
            "macro_miou": _mean([float(row["metrics"]["mean_iou"]) for row in full_scene]),
            "macro_overall_accuracy": _mean(
                [float(row["metrics"]["overall_accuracy"]) for row in full_scene]
            ),
        },
    }


def _group(rows: Sequence[Mapping[str, Any]], key) -> Dict[str, Any]:
    groups: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(key(row))].append(row)
    return {name: aggregate_rows(group) for name, group in sorted(groups.items())}


def summarize_condition(rows: Sequence[Mapping[str, Any]], condition: str) -> Dict[str, Any]:
    return {
        "condition": condition,
        "overall": aggregate_rows(rows),
        "by_language": _group(rows, lambda row: row["language"]),
        "by_ambiguity_level": _group(rows, lambda row: row["ambiguity_level"]),
        "by_gold_action_type": _group(rows, lambda row: row["gold_action_type"]),
        "by_task_type": _group(rows, lambda row: row["task_type"]),
        "by_language_and_level": _group(
            rows, lambda row: f"{row['language']}/{row['ambiguity_level']}"
        ),
    }


def _paired_bootstrap(
    baseline: Sequence[float], candidate: Sequence[float], samples: int, seed: int
) -> Dict[str, Any]:
    if len(baseline) != len(candidate) or not baseline:
        raise ValueError("paired bootstrap requires equal non-empty populations")
    differences = [candidate_value - baseline_value for baseline_value, candidate_value in zip(baseline, candidate)]
    rng = random.Random(seed)
    distribution = sorted(
        sum(differences[rng.randrange(len(differences))] for _ in differences) / len(differences)
        for _ in range(samples)
    )
    return {
        "delta": float(np.mean(differences)),
        "lower": distribution[int(samples * 0.025)],
        "upper": distribution[min(int(samples * 0.975), samples - 1)],
        "samples": samples,
        "seed": seed,
    }


def evaluate_task_aware_conditions(
    gold_path: Path,
    condition_paths: Mapping[str, Path],
    annotation_path: Path,
    data_root: Optional[Path],
    output_dir: Path,
    bootstrap_samples: int = 10000,
    bootstrap_seed: int = 20260809,
    reference_condition: Optional[str] = None,
) -> Dict[str, Any]:
    gold_records = [row for _, row in iter_jsonl(gold_path)]
    gold_ids = [extract_gold(row)[0] for row in gold_records]
    annotations = load_annotation_index(annotation_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    scored: Dict[str, List[Dict[str, Any]]] = {
        condition: [] for condition in condition_paths
    }
    conditions: Dict[str, Any] = {}
    runs_by_condition: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for condition, run_path in condition_paths.items():
        runs = {str(row.get("id", "")): row for _, row in iter_jsonl(run_path)}
        if set(runs) != set(gold_ids):
            raise ValueError(f"Condition {condition!r} does not match frozen population")
        runs_by_condition[condition] = runs

    # Evaluate all conditions for one request before advancing so its source
    # point cloud and proxy target are loaded only once.
    for record in gold_records:
        request_id, gold_request, _ = extract_gold(record)
        action = gold_request.get("action")
        action_type = str(action.get("type", "")) if isinstance(action, Mapping) else ""
        scene_data = None
        if action_type != "direct_answer":
            scene_data = _load_xyz_labels(_resolve_point_path(record, data_root))
        for condition, runs in runs_by_condition.items():
            scored[condition].append(
                score_request(
                    record,
                    runs[request_id],
                    annotations,
                    data_root,
                    scene_data=scene_data,
                )
            )

    for condition, rows in scored.items():
        conditions[condition] = summarize_condition(rows, condition)
        rows_path = output_dir / condition / "task_quality_rows.jsonl"
        rows_path.parent.mkdir(parents=True, exist_ok=True)
        rows_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        conditions[condition]["rows_path"] = str(rows_path)
        conditions[condition]["rows_sha256"] = sha256_file(rows_path)

    comparisons: Dict[str, Any] = {}
    selected_reference = reference_condition
    if len(scored) >= 2:
        if selected_reference is None:
            selected_reference = (
                "vaguehydro_lora" if "vaguehydro_lora" in scored else next(iter(scored))
            )
        if selected_reference not in scored:
            raise ValueError(f"Unknown reference condition {selected_reference!r}")
        candidate_by_id = {row["id"]: row for row in scored[selected_reference]}
        for baseline_name in scored:
            if baseline_name == selected_reference:
                continue
            baseline_by_id = {row["id"]: row for row in scored[baseline_name]}
            comparison = {
                "baseline": baseline_name,
                "candidate": selected_reference,
            "mean_per_request_task_score": _paired_bootstrap(
                [float(baseline_by_id[request_id]["task_score"]) for request_id in gold_ids],
                [float(candidate_by_id[request_id]["task_score"]) for request_id in gold_ids],
                bootstrap_samples,
                bootstrap_seed,
            ),
            "by_task_type": {},
            "by_language": {},
            "by_ambiguity_level": {},
            "by_gold_action_type": {},
        }
            for output_name, field_name in (
                ("by_task_type", "task_type"),
                ("by_language", "language"),
                ("by_ambiguity_level", "ambiguity_level"),
                ("by_gold_action_type", "gold_action_type"),
            ):
                values = sorted({str(row[field_name]) for row in scored[baseline_name]})
                for value in values:
                    ids = [
                        row["id"]
                        for row in scored[baseline_name]
                        if str(row[field_name]) == value
                    ]
                    comparison[output_name][value] = _paired_bootstrap(
                        [float(baseline_by_id[request_id]["task_score"]) for request_id in ids],
                        [float(candidate_by_id[request_id]["task_score"]) for request_id in ids],
                        bootstrap_samples,
                        bootstrap_seed,
                    )
            comparisons[baseline_name] = comparison

    return {
        "schema_version": TASK_AWARE_SCHEMA_VERSION,
        "status": "completed",
        "condition_count": len(conditions),
        "gold_count": len(gold_ids),
        "gold_path": str(gold_path),
        "gold_sha256": sha256_file(gold_path),
        "annotation_path": str(annotation_path),
        "annotation_sha256": sha256_file(annotation_path),
        "data_root": str(data_root) if data_root else None,
        "conditions": conditions,
        "reference_condition": selected_reference,
        "paired_comparisons_by_baseline": comparisons,
        "paired_comparison": next(iter(comparisons.values())) if len(comparisons) == 1 else None,
        "limitations": [
            "Class, attribute, relation, and no-target masks use dataset-derived proxy ground truth.",
            "The mixed mean_per_request_task_score averages heterogeneous bounded metrics and is reported with task-specific breakdowns.",
            "The multimodal segmentation adapter currently validates but does not use the image during inference.",
        ],
    }
