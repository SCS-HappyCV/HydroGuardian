from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import numpy as np

from hydro_remote_agent.evaluation.language_segmentation import binary_mask_metrics
from hydro_remote_agent.evaluation.routing import iter_jsonl


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [row for _, row in iter_jsonl(path)]


def _latest_rows(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("id", "")): row for row in _read_jsonl(path) if row.get("id")}


def _load_scene(point_path: Path) -> tuple[np.ndarray, np.ndarray]:
    points = np.loadtxt(point_path, dtype=np.float32)
    if points.ndim == 1:
        points = points.reshape(1, -1)
    if points.shape[1] < 7:
        raise ValueError(f"{point_path} must contain XYZRGB+label")
    return points[:, :3], points[:, 6].astype(np.int64)


def _target_mask(xyz: np.ndarray, labels: np.ndarray, supervision: Mapping[str, Any]) -> np.ndarray:
    rule = supervision.get("target_mask_rule")
    if isinstance(rule, Mapping):
        from wcs_unified.dataset import build_rule_target_mask
        import torch

        return build_rule_target_mask(
            torch.from_numpy(xyz), torch.from_numpy(labels), dict(rule)
        ).cpu().numpy().astype(bool)
    target = np.zeros(labels.shape[0], dtype=bool)
    if not bool(supervision.get("is_no_target", False)):
        for class_id in supervision.get("target_label_ids", []):
            target |= labels == int(class_id)
    return target


def _artifacts(result: Mapping[str, Any]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    groups: list[Any] = [result.get("terminal_artifacts")]
    workflow = result.get("workflow_result")
    if isinstance(workflow, Mapping):
        for step in workflow.get("steps", []):
            if isinstance(step, Mapping):
                step_result = step.get("result")
                if isinstance(step_result, Mapping):
                    groups.append(step_result.get("artifacts"))
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        for name, value in group.items():
            if isinstance(value, str) and value not in grouped[str(name)]:
                grouped[str(name)].append(value)
    return grouped


def _load_artifact(result: Mapping[str, Any], names: Iterable[str]) -> Optional[np.ndarray]:
    artifacts = _artifacts(result)
    for name in names:
        for value in artifacts.get(name, []):
            path = Path(value)
            if not path.is_file():
                continue
            with np.load(path, allow_pickle=False) as payload:
                key = name if name in payload.files else payload.files[0]
                return np.asarray(payload[key]).reshape(-1)
    return None


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


def _direct_metrics(gold_request: Mapping[str, Any], run: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    gold_action = gold_request.get("action", {})
    gold_answer = gold_action.get("answer") if isinstance(gold_action, Mapping) else None
    result = run.get("result") if isinstance(run, Mapping) else None
    answer = result.get("response") if isinstance(result, Mapping) else None
    gold_polarity = _polarity(gold_answer)
    predicted_polarity = _polarity(answer)
    semantic = bool(
        answer is not None
        and gold_polarity is not None
        and gold_polarity == predicted_polarity
    )
    return {
        "output_available": answer is not None,
        "semantic_correct": semantic,
        "gold_polarity": gold_polarity,
        "predicted_polarity": predicted_polarity,
    }


def _dense_metrics(
    claim: Mapping[str, Any],
    run: Optional[Mapping[str, Any]],
    data_root: Path,
) -> dict[str, Any]:
    sample_id = str(claim.get("sample_id", ""))
    region_id, patch_id = sample_id.split("_", 1)
    point_path = data_root / region_id / "velodyne" / f"{patch_id}.txt"
    try:
        xyz, labels = _load_scene(point_path)
        target = _target_mask(xyz, labels, claim["supervision"])
    except Exception as exc:
        return {
            "output_available": False,
            "iou": 0.0,
            "dice": 0.0,
            "error": f"{type(exc).__name__}: {exc}",
        }
    result = run.get("result") if isinstance(run, Mapping) else None
    execution_succeeded = bool(
        isinstance(run, Mapping)
        and run.get("status") == "succeeded"
        and isinstance(result, Mapping)
    )
    prediction = (
        _load_artifact(result, ("relation_mask", "target_mask"))
        if isinstance(result, Mapping)
        else None
    )
    if prediction is None and isinstance(result, Mapping):
        point_labels = _load_artifact(result, ("point_labels",))
        target_ids = [
            int(value)
            for value in claim["supervision"].get("target_label_ids", [])
        ]
        if point_labels is not None and point_labels.shape == labels.shape:
            prediction = np.zeros(labels.shape[0], dtype=bool)
            for target_id in target_ids:
                prediction |= point_labels == target_id
    available = prediction is not None and prediction.shape == target.shape
    metrics = binary_mask_metrics(target, prediction) if available else binary_mask_metrics(
        target, np.zeros_like(target)
    )
    return {
        "output_available": bool(available and execution_succeeded),
        "execution_succeeded": execution_succeeded,
        "iou": float(metrics["iou"]) if available else 0.0,
        "dice": float(metrics["dice"]) if available else 0.0,
        "target_points": int(metrics["target_points"]),
        "predicted_points": int(metrics["predicted_points"]) if available else 0,
        "is_no_target": bool(claim["supervision"].get("is_no_target", False)),
        "predicted_no_target": bool(available and metrics["predicted_points"] == 0),
    }


def _claim_row(
    compound: Mapping[str, Any],
    claim_index: int,
    run: Optional[Mapping[str, Any]],
    data_root: Path,
) -> dict[str, Any]:
    claim = dict(compound["claims"][claim_index])
    claim["sample_id"] = compound["sample_id"]
    if claim_index == 0:
        metrics = _direct_metrics(claim["gold_request"], run)
        metrics.update(
            {
                "claim_index": 0,
                "claim_role": claim.get("role", ""),
                "canonical_intent": claim.get("canonical_intent", ""),
            }
        )
        return metrics
    metrics = _dense_metrics(claim, run, data_root)
    metrics.update(
        {
            "claim_index": 1,
            "claim_role": claim.get("role", ""),
            "canonical_intent": claim.get("canonical_intent", ""),
        }
    )
    return metrics


def _condition_rows(
    compounds: list[Mapping[str, Any]],
    predictions_path: Path,
    execution_path: Path,
    data_root: Path,
    condition: str,
) -> list[dict[str, Any]]:
    prediction_rows = _latest_rows(predictions_path)
    execution_rows = _latest_rows(execution_path) if execution_path.is_file() else {}
    output: list[dict[str, Any]] = []
    for compound in compounds:
        compound_id = str(compound["compound_id"])
        if condition in {"claimwise_rule_decomposition", "learned_claimwise"}:
            prediction_rows_for_compound = [
                prediction_rows.get(f"{compound_id}:claim{claim_index}")
                for claim_index in (0, 1)
            ]
        else:
            prediction_rows_for_compound = [prediction_rows.get(compound_id)]
        for prediction in prediction_rows_for_compound:
            if prediction is None:
                raise ValueError(f"Missing prediction row for {compound_id}")
            claim_index = int(prediction["claim_index"])
            run_id = str(prediction["id"])
            run = execution_rows.get(run_id)
            output.append(
                {
                    "compound_id": compound_id,
                    "sample_id": str(compound["sample_id"]),
                    "claim": _claim_row(compound, claim_index, run, data_root),
                    "run_status": run.get("status") if run else "missing",
                    "duration_ms": (
                        (run.get("result") or {}).get("duration_ms")
                        if isinstance(run, Mapping)
                        else None
                    ),
                    "required_tools": (
                        (run.get("result") or {}).get("required_tools", [])
                        if isinstance(run, Mapping)
                        else []
                    ),
                }
            )
    return output


def summarize_condition(rows: list[Mapping[str, Any]], condition: str) -> dict[str, Any]:
    direct = [row["claim"] for row in rows if int(row["claim"]["claim_index"]) == 0]
    dense = [row["claim"] for row in rows if int(row["claim"]["claim_index"]) == 1]
    direct_available = [row for row in direct if row["output_available"]]
    dense_available = [row for row in dense if row["output_available"]]
    direct_correct = [row for row in direct if row["semantic_correct"]]
    dense_ious = [float(row["iou"]) for row in dense]
    duration = [
        float(row["duration_ms"])
        for row in rows
        if row.get("duration_ms") is not None
    ]
    by_intent: dict[str, list[float]] = defaultdict(list)
    for row in dense:
        by_intent[str(row["canonical_intent"])].append(float(row["iou"]))
    compound_ids = sorted({str(row["compound_id"]) for row in rows})
    direct_by_compound = {
        str(row["compound_id"]): row["claim"]
        for row in rows
        if int(row["claim"]["claim_index"]) == 0
    }
    dense_by_compound = {
        str(row["compound_id"]): row["claim"]
        for row in rows
        if int(row["claim"]["claim_index"]) == 1
    }
    complete_pairs = [
        (direct_by_compound[compound_id], dense_by_compound[compound_id])
        for compound_id in compound_ids
        if compound_id in direct_by_compound and compound_id in dense_by_compound
    ]
    claim_count = len(rows)
    return {
        "schema_version": "cmge.condition_eval.v1",
        "condition": condition,
        "compound_count": len(compound_ids),
        "claim_count": claim_count,
        "direct": {
            "count": len(direct),
            "output_availability": len(direct_available) / len(direct) if direct else None,
            "semantic_accuracy": len(direct_correct) / len(direct) if direct else None,
        },
        "dense": {
            "count": len(dense),
            "output_availability": len(dense_available) / len(dense) if dense else None,
            "macro_iou": float(np.mean(dense_ious)) if dense_ious else None,
            "macro_dice": float(np.mean([float(row["dice"]) for row in dense])) if dense else None,
            "by_intent_macro_iou": {
                name: float(np.mean(values)) for name, values in sorted(by_intent.items())
            },
        },
        "claim_coverage": (
            sum(
                bool(row["output_available"])
                for row in direct + dense
            )
            / (len(direct) + len(dense))
            if direct or dense
            else None
        ),
        "complete_request_coverage": (
            sum(
                bool(direct_row["output_available"] and dense_row["output_available"])
                for direct_row, dense_row in complete_pairs
            )
            / len(compound_ids)
            if compound_ids
            else None
        ),
        "complete_request_correctness_iou_0_5": (
            sum(
                bool(
                    direct_row["semantic_correct"]
                    and dense_row["output_available"]
                    and float(dense_row["iou"]) >= 0.5
                )
                for direct_row, dense_row in complete_pairs
            )
            / len(compound_ids)
            if compound_ids
            else None
        ),
        "mean_duration_ms": float(np.mean(duration)) if duration else None,
        "median_duration_ms": float(np.median(duration)) if duration else None,
        "total_tool_calls": int(sum(len(row.get("required_tools", [])) for row in rows)),
        "missing_execution_count": sum(row["run_status"] == "missing" for row in rows),
    }


def evaluate(
    compounds_path: Path,
    conditions_dir: Path,
    data_root: Path,
    output: Path,
    conditions: tuple[str, ...] = (
        "direct_only",
        "dense_only",
        "claimwise_rule_decomposition",
    ),
) -> dict[str, Any]:
    compounds = _read_jsonl(compounds_path)
    condition_reports = {}
    for condition in conditions:
        condition_dir = conditions_dir / condition
        predictions = condition_dir / "predictions.jsonl"
        execution = condition_dir / "execution.jsonl"
        rows = _condition_rows(compounds, predictions, execution, data_root, condition)
        condition_reports[condition] = summarize_condition(rows, condition)
        (condition_dir / "scored_claims.jsonl").parent.mkdir(parents=True, exist_ok=True)
        with (condition_dir / "scored_claims.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    report = {
        "schema_version": "cmge.eval.v1",
        "compound_count": len(compounds),
        "data_root": str(data_root),
        "conditions": condition_reports,
        "interpretation": (
            "Learned claim-wise conditions include planner routing and generated requests; "
            "gold rule conditions isolate expert execution quality."
            if "learned_claimwise" in conditions
            else "This pilot executes gold component actions. It measures decomposition and "
            "expert-output coverage, not learned planner routing accuracy."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate CMGE compound execution conditions.")
    parser.add_argument("--compounds", required=True, type=Path)
    parser.add_argument("--conditions-dir", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--condition",
        action="append",
        choices=("direct_only", "dense_only", "claimwise_rule_decomposition", "learned_claimwise"),
        help="Condition to evaluate; may be repeated. Defaults to the three pilot conditions.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    conditions = tuple(args.condition) if args.condition else (
        "direct_only",
        "dense_only",
        "claimwise_rule_decomposition",
    )
    report = evaluate(
        args.compounds,
        args.conditions_dir,
        args.data_root,
        args.output,
        conditions,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
