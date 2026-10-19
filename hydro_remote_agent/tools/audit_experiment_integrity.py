from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from hydro_remote_agent.evaluation.language_segmentation import summarize_language_segmentation_rows
from hydro_remote_agent.evaluation.routing import (
    canonical_json,
    extract_gold,
    iter_jsonl,
    parse_json_response,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _rows(path: Path) -> list[dict[str, Any]]:
    return [dict(row) for _, row in iter_jsonl(path)]


def _ids(rows: Iterable[Mapping[str, Any]], key: str) -> list[str]:
    return [str(row.get(key, "")) for row in rows]


def _lookup(payload: Mapping[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise KeyError(dotted_path)
        value = value[part]
    return value


class Audit:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(
        self,
        check_id: str,
        passed: bool,
        details: str,
        evidence: Optional[Mapping[str, Any]] = None,
        severity: str = "fail",
    ) -> None:
        self.checks.append(
            {
                "id": check_id,
                "status": "pass" if passed else severity,
                "details": details,
                "evidence": dict(evidence or {}),
            }
        )

    @property
    def status(self) -> str:
        statuses = {check["status"] for check in self.checks}
        if "fail" in statuses:
            return "fail"
        if "warn" in statuses:
            return "warn"
        return "pass"


def _same_number(left: Any, right: Any, tolerance: float = 1e-10) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tolerance
    return left == right


def run_audit(
    project_root: Path,
    protocol_path: Path,
    ledger_path: Path,
    split_root: Path,
) -> dict[str, Any]:
    audit = Audit()
    protocol = _load_json(protocol_path)
    ledger = _load_json(ledger_path)

    audit.add(
        "protocol_hash",
        ledger.get("protocol_sha256") == _sha256(protocol_path),
        "Ledger protocol hash matches the frozen protocol file.",
        {"actual": _sha256(protocol_path), "ledger": ledger.get("protocol_sha256")},
    )

    split_sets: dict[str, set[str]] = {}
    for partition in ("train", "val", "test"):
        path = split_root / f"{partition}.txt"
        manifest_path = split_root / f"{partition}.jsonl"
        values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        split_sets[partition] = set(values)
        expected = protocol["split"]["partitions"][partition]
        audit.add(
            f"split_{partition}",
            len(values) == len(set(values)) == expected["samples"]
            and manifest_path.is_file()
            and _sha256(manifest_path) == expected["sha256"],
            f"Frozen {partition} ID count and JSONL manifest SHA256 match protocol.",
            {
                "count": len(values),
                "unique": len(set(values)),
                "manifest_sha256": _sha256(manifest_path) if manifest_path.is_file() else None,
            },
        )
    overlap = {
        "train_val": len(split_sets["train"] & split_sets["val"]),
        "train_test": len(split_sets["train"] & split_sets["test"]),
        "val_test": len(split_sets["val"] & split_sets["test"]),
    }
    audit.add("split_disjoint", not any(overlap.values()), "Frozen partitions are pairwise disjoint.", overlap)

    ledger_by_id = {run["run_id"]: run for run in ledger.get("runs", [])}
    run_failures = []
    for spec in protocol.get("runs", []):
        record = ledger_by_id.get(spec["run_id"])
        report_path = project_root / spec["report"]
        if record is None or not report_path.is_file():
            run_failures.append({"run_id": spec["run_id"], "reason": "missing_record_or_report"})
            continue
        report = _load_json(report_path)
        if record.get("report_sha256") != _sha256(report_path):
            run_failures.append({"run_id": spec["run_id"], "reason": "report_hash_mismatch"})
        for metric_path, value in record.get("metrics", {}).items():
            try:
                actual = _lookup(report, metric_path)
            except KeyError:
                run_failures.append({"run_id": spec["run_id"], "reason": f"missing_metric:{metric_path}"})
                continue
            if not _same_number(actual, value):
                run_failures.append({"run_id": spec["run_id"], "reason": f"metric_mismatch:{metric_path}"})
        expected_status = "failed" if spec.get("role") == "formal_stress" else "completed"
        if record.get("status") != expected_status:
            run_failures.append(
                {"run_id": spec["run_id"], "reason": f"status:{record.get('status')}!={expected_status}"}
            )
    audit.add(
        "ledger_reports",
        not run_failures,
        "Every protocol run has a hash-matched report and exact metric values; the declared stress failure remains failed.",
        {"run_count": len(protocol.get("runs", [])), "failures": run_failures},
    )

    predictions_path = project_root / "runs/hydro_remote_agent/agent_eval_v1/adapter_predictions_240.jsonl"
    execution_path = project_root / "runs/hydro_remote_agent/agent_execution_eval_v1/execution_results_complete_calibrated_240.jsonl"
    prediction_rows = _rows(predictions_path)
    execution_rows = _rows(execution_path)
    prediction_ids = _ids(prediction_rows, "id")
    execution_ids = _ids(execution_rows, "id")
    execution_ok = (
        len(prediction_ids) == len(set(prediction_ids)) == 240
        and len(execution_ids) == len(set(execution_ids)) == 240
        and set(prediction_ids) == set(execution_ids)
        and all(row.get("status") == "succeeded" for row in execution_rows)
    )
    audit.add(
        "agent_execution_population",
        execution_ok,
        "Frozen predictions and complete execution contain the same 240 unique successful requests.",
        {"prediction_count": len(prediction_ids), "execution_count": len(execution_ids)},
    )
    manifest_paths = [
        Path(str(row["result"]["manifest_path"]))
        for row in execution_rows
        if isinstance(row.get("result"), Mapping) and row["result"].get("manifest_path")
    ]
    audit.add(
        "agent_execution_manifests",
        len(manifest_paths) == 240 and all(path.is_file() for path in manifest_paths),
        "All 240 Agent execution manifests exist on the evaluation host.",
        {"declared": len(manifest_paths), "existing": sum(path.is_file() for path in manifest_paths)},
        severity="warn",
    )

    language_dir = project_root / "runs/hydro_remote_agent/expert_quality_v1/language_guided_final_best_calibrated_v2"
    language_results = _rows(language_dir / "results.jsonl")
    language_ids = _ids(language_results, "request_id")
    language_report = _load_json(language_dir / "report.json")
    recomputed = summarize_language_segmentation_rows(language_results, expected_count=1903)
    metric_paths = (
        "overall.macro_iou",
        "overall.micro_iou",
        "overall.macro_dice",
        "overall.no_target_precision",
        "overall.no_target_recall",
        "overall.no_target_f1",
        "by_task_type.class.macro_iou",
        "by_task_type.attribute.macro_iou",
        "by_task_type.relation.macro_iou",
        "by_task_type.no_target.macro_iou",
    )
    recompute_failures = [
        path
        for path in metric_paths
        if not _same_number(_lookup(language_report, path), _lookup(recomputed, path))
    ]
    task_counts: dict[str, int] = {}
    for row in language_results:
        task = str(row.get("task_type", "unknown"))
        task_counts[task] = task_counts.get(task, 0) + 1
    expected_task_counts = {"attribute": 781, "class": 539, "relation": 333, "no_target": 250}
    audit.add(
        "language_results_recomputed",
        len(language_ids) == len(set(language_ids)) == 1903
        and all(row.get("status") == "succeeded" for row in language_results)
        and task_counts == expected_task_counts
        and not recompute_failures,
        "Language metrics are reproducible from 1,903 unique per-request rows with the frozen task composition.",
        {"task_counts": task_counts, "metric_mismatches": recompute_failures},
    )
    language_manifests = [Path(str(row.get("manifest_path", ""))) for row in language_results]
    audit.add(
        "language_manifests",
        len(language_manifests) == 1903 and all(path.is_file() for path in language_manifests),
        "All 1,903 language-expert invocation manifests exist on the evaluation host.",
        {"declared": len(language_manifests), "existing": sum(path.is_file() for path in language_manifests)},
        severity="warn",
    )

    calibration_path = project_root / "runs/hydro_remote_agent/expert_quality_v1/language_calibration_val_v1/runtime_calibration.json"
    calibration = _load_json(calibration_path)
    calibration_ids: set[str] = set()
    missing_calibration_sources = []
    for source in calibration.get("source_results", []):
        source_path = Path(source)
        if not source_path.is_file():
            missing_calibration_sources.append(str(source_path))
            continue
        calibration_ids.update(str(row.get("sample_id", "")) for row in _rows(source_path))
    calibration_clean = (
        not missing_calibration_sources
        and bool(calibration_ids)
        and calibration_ids <= split_sets["val"]
        and not (calibration_ids & split_sets["test"])
    )
    audit.add(
        "calibration_split_isolation",
        calibration_clean,
        "Threshold and no-target calibration rows come only from validation tiles and do not overlap test tiles.",
        {
            "calibration_tile_count": len(calibration_ids),
            "test_overlap": len(calibration_ids & split_sets["test"]),
            "missing_sources": missing_calibration_sources,
        },
        severity="warn",
    )

    baseline_hash = _sha256(execution_path)
    ablation_failures = []
    expected_affected = {"no_verifier": 160, "no_workflow": 80, "no_language_expert": 50}
    for mode, affected in expected_affected.items():
        root = project_root / f"runs/hydro_remote_agent/system_ablations_v1/{mode}"
        report = _load_json(root / "report.json")
        rows = _rows(root / "execution_results.jsonl")
        if report["ablation"].get("baseline_results_sha256") != baseline_hash:
            ablation_failures.append({"mode": mode, "reason": "baseline_hash"})
        if report["ablation"].get("affected_request_count") != affected:
            ablation_failures.append({"mode": mode, "reason": "affected_count"})
        if set(_ids(rows, "id")) != set(execution_ids) or len(rows) != 240:
            ablation_failures.append({"mode": mode, "reason": "population"})
    audit.add(
        "system_ablation_lineage",
        not ablation_failures,
        "All system ablations preserve the 240-request population and reference the exact complete-execution SHA256.",
        {"baseline_sha256": baseline_hash, "failures": ablation_failures},
    )

    comparison_path = project_root / "runs/hydro_remote_agent/agent_multi_baseline_v1/comparison_report.json"
    comparison = _load_json(comparison_path)
    baseline_failures = []
    expected_conditions = {
        "rule_router",
        "backbone_minimal",
        "backbone_full",
        "backbone_react_style",
        "vaguehydro_lora",
    }
    condition_payloads = comparison.get("conditions", {})
    if set(condition_payloads) != expected_conditions:
        baseline_failures.append({"reason": "condition_set", "actual": sorted(condition_payloads)})
    for condition_id, payload in condition_payloads.items():
        prediction_path = project_root / str(payload.get("prediction_path", ""))
        if not prediction_path.is_file():
            baseline_failures.append({"condition": condition_id, "reason": "missing_predictions"})
            continue
        rows = _rows(prediction_path)
        ids = _ids(rows, "id")
        if len(ids) != len(set(ids)) or set(ids) != set(prediction_ids):
            baseline_failures.append({"condition": condition_id, "reason": "population"})
        if payload.get("prediction_sha256") != _sha256(prediction_path):
            baseline_failures.append({"condition": condition_id, "reason": "prediction_hash"})
    audit.add(
        "multi_baseline_population",
        comparison.get("status") == "complete"
        and comparison.get("gold_count") == 240
        and comparison.get("condition_count") == 5
        and not baseline_failures,
        "All five Agent baselines contain the exact frozen 240-request population and hash-matched predictions.",
        {"condition_count": len(condition_payloads), "failures": baseline_failures},
    )

    task_aware_240_root = project_root / "runs/hydro_remote_agent/agent_task_aware_e2e_240"
    task_aware_240_protocol = _load_json(
        project_root / "hydro_remote_agent/configs/agent_task_aware_e2e_240.json"
    )
    task_aware_240_gold = project_root / str(task_aware_240_protocol["gold"]["path"])
    task_aware_240_gold_rows = _rows(task_aware_240_gold)
    task_aware_240_gold_ids = _ids(task_aware_240_gold_rows, "id")
    task_aware_240_conditions = {
        str(condition["id"])
        for condition in task_aware_240_protocol.get("conditions", [])
    }
    task_aware_240_report = _load_json(task_aware_240_root / "comparison_report.json")
    task_aware_240_failures = []
    if (
        len(task_aware_240_gold_ids) != 240
        or len(set(task_aware_240_gold_ids)) != 240
        or task_aware_240_protocol["gold"].get("sha256") != _sha256(task_aware_240_gold)
    ):
        task_aware_240_failures.append({"reason": "gold_population_or_hash"})
    if set(task_aware_240_report.get("conditions", {})) != task_aware_240_conditions:
        task_aware_240_failures.append({"reason": "condition_set"})
    for condition_id in sorted(task_aware_240_conditions):
        run_path = task_aware_240_root / condition_id / "run_240.jsonl"
        run_rows = _rows(run_path)
        run_ids = _ids(run_rows, "id")
        if (
            len(run_ids) != 240
            or len(set(run_ids)) != 240
            or set(run_ids) != set(task_aware_240_gold_ids)
        ):
            task_aware_240_failures.append(
                {"condition": condition_id, "reason": "population"}
            )
        if task_aware_240_report.get("run_sha256", {}).get(condition_id) != _sha256(run_path):
            task_aware_240_failures.append(
                {"condition": condition_id, "reason": "run_hash"}
            )
    merge_manifest = _load_json(
        task_aware_240_root / "vaguehydro_lora/merge_manifest.json"
    )
    if (
        merge_manifest.get("gold_sha256") != _sha256(task_aware_240_gold)
        or merge_manifest.get("prediction_sha256") != _sha256(predictions_path)
        or merge_manifest.get("execution_sha256") != _sha256(execution_path)
    ):
        task_aware_240_failures.append({"reason": "vaguehydro_merge_lineage"})
    audit.add(
        "task_aware_240_e2e_population",
        task_aware_240_report.get("status") == "completed"
        and not task_aware_240_failures,
        "All configured E2E conditions cover the exact frozen 240-request population with hash-matched real executions.",
        {
            "condition_count": len(task_aware_240_report.get("conditions", {})),
            "failures": task_aware_240_failures,
        },
    )

    task_aware_240_quality_root = task_aware_240_root / "task_aware_quality_v1"
    task_aware_240_quality_report = _load_json(
        task_aware_240_quality_root / "report.json"
    )
    task_aware_240_quality_failures = []
    if set(task_aware_240_quality_report.get("conditions", {})) != task_aware_240_conditions:
        task_aware_240_quality_failures.append({"reason": "condition_set"})
    for condition_id in sorted(task_aware_240_conditions):
        rows_path = task_aware_240_quality_root / condition_id / "task_quality_rows.jsonl"
        rows = _rows(rows_path)
        row_ids = _ids(rows, "id")
        if (
            len(row_ids) != 240
            or len(set(row_ids)) != 240
            or set(row_ids) != set(task_aware_240_gold_ids)
        ):
            task_aware_240_quality_failures.append(
                {"condition": condition_id, "reason": "population"}
            )
        condition = task_aware_240_quality_report.get("conditions", {}).get(
            condition_id, {}
        )
        if condition.get("rows_sha256") != _sha256(rows_path):
            task_aware_240_quality_failures.append(
                {"condition": condition_id, "reason": "rows_hash"}
            )
    audit.add(
        "task_aware_240_quality_population",
        task_aware_240_quality_report.get("status") == "completed"
        and task_aware_240_quality_report.get("gold_count") == 240
        and not task_aware_240_quality_failures,
        "Task-aware quality covers all configured conditions and every frozen request without dropping missing outputs.",
        {
            "condition_count": len(task_aware_240_quality_report.get("conditions", {})),
            "failures": task_aware_240_quality_failures,
        },
    )

    e2e_root = project_root / "runs/hydro_remote_agent/agent_e2e_comparison_v1"
    e2e_gold_path = e2e_root / "gold_50.jsonl"
    e2e_report_path = e2e_root / "comparison_report.json"
    e2e_manifest_path = e2e_root / "subset_manifest.json"
    e2e_failures = []
    e2e_gold_rows = _rows(e2e_gold_path)
    e2e_gold_ids = _ids(e2e_gold_rows, "id")
    e2e_report = _load_json(e2e_report_path)
    e2e_manifest = _load_json(e2e_manifest_path)
    expected_e2e_conditions = {"tool_observation_react", "vaguehydro_lora"}
    if len(e2e_gold_ids) != 50 or len(set(e2e_gold_ids)) != 50:
        e2e_failures.append({"reason": "gold_population", "count": len(e2e_gold_ids)})
    if set(e2e_report.get("conditions", {})) != expected_e2e_conditions:
        e2e_failures.append({"reason": "condition_set"})
    for condition_id in sorted(expected_e2e_conditions):
        run_path = e2e_root / condition_id / "run_50.jsonl"
        run_rows = _rows(run_path)
        run_ids = _ids(run_rows, "id")
        if len(run_ids) != 50 or len(set(run_ids)) != 50 or set(run_ids) != set(e2e_gold_ids):
            e2e_failures.append({"condition": condition_id, "reason": "population"})
        if e2e_report.get("run_sha256", {}).get(condition_id) != _sha256(run_path):
            e2e_failures.append({"condition": condition_id, "reason": "run_hash"})
    audit.add(
        "e2e_baseline_population",
        e2e_report.get("status") == "completed"
        and e2e_manifest.get("selected_count") == 50
        and e2e_manifest.get("observed_action_counts")
        == {"direct_answer": 10, "tool_call": 20, "workflow": 20}
        and e2e_manifest.get("observed_language_counts") == {"en": 25, "zh": 25}
        and not e2e_failures,
        "Both E2E conditions contain the same frozen balanced 50-request population and hash-matched traces.",
        {"gold_count": len(e2e_gold_ids), "failures": e2e_failures},
    )

    task_quality_root = e2e_root / "task_aware_quality_v1"
    task_quality_report = _load_json(task_quality_root / "report.json")
    task_quality_failures = []
    task_conditions = task_quality_report.get("conditions", {})
    if set(task_conditions) != expected_e2e_conditions:
        task_quality_failures.append({"reason": "condition_set"})
    for condition_id in sorted(expected_e2e_conditions):
        rows_path = task_quality_root / condition_id / "task_quality_rows.jsonl"
        rows = _rows(rows_path)
        row_ids = _ids(rows, "id")
        if len(row_ids) != 50 or len(set(row_ids)) != 50 or set(row_ids) != set(e2e_gold_ids):
            task_quality_failures.append({"condition": condition_id, "reason": "population"})
        condition = task_conditions.get(condition_id, {})
        if condition.get("rows_sha256") != _sha256(rows_path):
            task_quality_failures.append({"condition": condition_id, "reason": "rows_hash"})
        unknown_statuses = sorted(
            {
                str(row.get("score_status"))
                for row in rows
                if row.get("score_status") not in {"scored", "missing_required_output"}
            }
        )
        if unknown_statuses:
            task_quality_failures.append(
                {"condition": condition_id, "reason": "score_status", "values": unknown_statuses}
            )
    audit.add(
        "task_aware_quality_population",
        task_quality_report.get("status") == "completed"
        and task_quality_report.get("gold_count") == 50
        and not task_quality_failures,
        "Task-aware quality rows cover both frozen 50-request conditions with hash-matched per-request scores.",
        {"condition_count": len(task_conditions), "failures": task_quality_failures},
    )

    external_root = project_root / "runs/hydro_remote_agent/external_baselines_v1"
    external_protocol = _load_json(
        project_root / "hydro_remote_agent/configs/external_agent_comparison_v1.json"
    )
    external_report = _load_json(external_root / "comparison_report.json")
    external_manifest = _load_json(external_root / "model_manifest.json")
    expected_external_conditions = {
        "tool_observation_react",
        "glm46v_flash_toolspec",
        "vaguehydro_lora",
    }
    external_failures = []
    if external_protocol.get("gold", {}).get("sha256") != _sha256(e2e_gold_path):
        external_failures.append({"reason": "protocol_gold_hash"})
    if set(external_report.get("conditions", {})) != expected_external_conditions:
        external_failures.append({"reason": "condition_set"})
    external_run_paths = {
        "tool_observation_react": e2e_root / "tool_observation_react/run_50.jsonl",
        "glm46v_flash_toolspec": external_root / "glm46v_flash_toolspec/run_50.jsonl",
        "vaguehydro_lora": e2e_root / "vaguehydro_lora/run_50.jsonl",
    }
    for condition_id, run_path in external_run_paths.items():
        run_ids = _ids(_rows(run_path), "id")
        if len(run_ids) != 50 or len(set(run_ids)) != 50 or set(run_ids) != set(e2e_gold_ids):
            external_failures.append({"condition": condition_id, "reason": "population"})
        if external_report.get("run_sha256", {}).get(condition_id) != _sha256(run_path):
            external_failures.append({"condition": condition_id, "reason": "run_hash"})
    if (
        external_manifest.get("model_id") != "zai-org/GLM-4.6V-Flash"
        or external_manifest.get("weight_shard_count") != 4
        or len(external_manifest.get("weight_shard_sha256", {})) != 4
    ):
        external_failures.append({"reason": "model_manifest"})
    audit.add(
        "external_agent_baseline_population",
        external_report.get("status") == "completed" and not external_failures,
        "Independent GLM, ReAct, and VagueHydro conditions share the frozen 50-request population and hash-matched traces.",
        {"condition_count": len(external_report.get("conditions", {})), "failures": external_failures},
    )

    external_task_root = external_root / "task_aware_quality_v1"
    external_task_report = _load_json(external_task_root / "report.json")
    external_task_failures = []
    if set(external_task_report.get("conditions", {})) != expected_external_conditions:
        external_task_failures.append({"reason": "condition_set"})
    for condition_id in sorted(expected_external_conditions):
        rows_path = external_task_root / condition_id / "task_quality_rows.jsonl"
        rows = _rows(rows_path)
        row_ids = _ids(rows, "id")
        if len(row_ids) != 50 or len(set(row_ids)) != 50 or set(row_ids) != set(e2e_gold_ids):
            external_task_failures.append({"condition": condition_id, "reason": "population"})
        condition = external_task_report.get("conditions", {}).get(condition_id, {})
        if condition.get("rows_sha256") != _sha256(rows_path):
            external_task_failures.append({"condition": condition_id, "reason": "rows_hash"})
    audit.add(
        "external_task_aware_quality_population",
        external_task_report.get("status") == "completed" and not external_task_failures,
        "External task-aware quality covers all three frozen conditions with hash-matched per-request scores.",
        {"condition_count": len(external_task_report.get("conditions", {})), "failures": external_task_failures},
    )

    external_v2_root = project_root / "runs/hydro_remote_agent/external_agent_comparison_v2"
    external_v2_protocol = _load_json(
        project_root / "hydro_remote_agent/configs/external_agent_comparison_v2.json"
    )
    external_v2_report = _load_json(external_v2_root / "comparison_report.json")
    expected_external_v2_conditions = expected_external_conditions | {
        "deepseek_vl2_small_toolspec"
    }
    external_v2_run_paths = {
        **external_run_paths,
        "deepseek_vl2_small_toolspec": project_root
        / "runs/hydro_remote_agent/external_deepseek_vl2_v1/deepseek_vl2_small_toolspec/run_50.jsonl",
    }
    external_v2_failures = []
    if external_v2_protocol.get("gold", {}).get("sha256") != _sha256(e2e_gold_path):
        external_v2_failures.append({"reason": "protocol_gold_hash"})
    if set(external_v2_report.get("conditions", {})) != expected_external_v2_conditions:
        external_v2_failures.append({"reason": "condition_set"})
    for condition_id, run_path in external_v2_run_paths.items():
        run_ids = _ids(_rows(run_path), "id")
        if len(run_ids) != 50 or len(set(run_ids)) != 50 or set(run_ids) != set(e2e_gold_ids):
            external_v2_failures.append({"condition": condition_id, "reason": "population"})
        if external_v2_report.get("run_sha256", {}).get(condition_id) != _sha256(run_path):
            external_v2_failures.append({"condition": condition_id, "reason": "run_hash"})
    deepseek_manifest = _load_json(
        project_root
        / "runs/hydro_remote_agent/external_agent_comparison_v2/model_manifests/deepseek-vl2-small_manifest.json"
    )
    if (
        deepseek_manifest.get("model_id") != "deepseek-ai/deepseek-vl2-small"
        or deepseek_manifest.get("weight_shard_count") != 4
        or len(deepseek_manifest.get("weight_shard_sha256", {})) != 4
    ):
        external_v2_failures.append({"reason": "deepseek_model_manifest"})
    audit.add(
        "external_agent_multi_family_population",
        external_v2_report.get("status") == "completed" and not external_v2_failures,
        "GLM, DeepSeek-VL2, ReAct, and VagueHydro share the frozen 50-request population and hash-matched traces.",
        {
            "condition_count": len(external_v2_report.get("conditions", {})),
            "failures": external_v2_failures,
        },
    )

    external_v2_task_root = external_v2_root / "task_aware_quality_v1"
    external_v2_task_report = _load_json(external_v2_task_root / "report.json")
    external_v2_task_failures = []
    if set(external_v2_task_report.get("conditions", {})) != expected_external_v2_conditions:
        external_v2_task_failures.append({"reason": "condition_set"})
    for condition_id in sorted(expected_external_v2_conditions):
        rows_path = external_v2_task_root / condition_id / "task_quality_rows.jsonl"
        rows = _rows(rows_path)
        row_ids = _ids(rows, "id")
        if len(row_ids) != 50 or len(set(row_ids)) != 50 or set(row_ids) != set(e2e_gold_ids):
            external_v2_task_failures.append(
                {"condition": condition_id, "reason": "population"}
            )
        condition = external_v2_task_report.get("conditions", {}).get(condition_id, {})
        if condition.get("rows_sha256") != _sha256(rows_path):
            external_v2_task_failures.append(
                {"condition": condition_id, "reason": "rows_hash"}
            )
    audit.add(
        "external_multi_family_task_aware_quality_population",
        external_v2_task_report.get("status") == "completed"
        and not external_v2_task_failures,
        "Multi-family external task-aware quality covers all four frozen conditions with hash-matched rows.",
        {
            "condition_count": len(external_v2_task_report.get("conditions", {})),
            "failures": external_v2_task_failures,
        },
    )

    external_v3_root = project_root / "runs/hydro_remote_agent/external_agent_comparison_v3"
    external_v3_protocol = _load_json(
        project_root / "hydro_remote_agent/configs/external_agent_comparison_v3.json"
    )
    external_v3_report = _load_json(external_v3_root / "comparison_report.json")
    schema_condition = "deepseek_vl2_small_schema_constrained"
    expected_external_v3_conditions = expected_external_v2_conditions | {
        schema_condition
    }
    external_v3_run_paths = {
        **external_v2_run_paths,
        schema_condition: project_root
        / "runs/hydro_remote_agent/external_deepseek_vl2_schema_v1"
        / schema_condition
        / "run_50.jsonl",
    }
    external_v3_failures = []
    if external_v3_protocol.get("gold", {}).get("sha256") != _sha256(e2e_gold_path):
        external_v3_failures.append({"reason": "protocol_gold_hash"})
    if set(external_v3_report.get("conditions", {})) != expected_external_v3_conditions:
        external_v3_failures.append({"reason": "condition_set"})
    protocol_schema = next(
        (
            item
            for item in external_v3_protocol.get("conditions", [])
            if item.get("id") == schema_condition
        ),
        {},
    )
    if (
        protocol_schema.get("constraint_mode")
        != "token_level_agent_request_json_schema"
        or protocol_schema.get("post_generation_repair") is not False
        or external_v3_protocol.get("fairness", {}).get(
            "ground_truth_and_metadata_hidden_from_planner"
        )
        is not True
    ):
        external_v3_failures.append({"reason": "schema_constraint_protocol"})
    for condition_id, run_path in external_v3_run_paths.items():
        run_ids = _ids(_rows(run_path), "id")
        if len(run_ids) != 50 or len(set(run_ids)) != 50 or set(run_ids) != set(e2e_gold_ids):
            external_v3_failures.append(
                {"condition": condition_id, "reason": "population"}
            )
        if external_v3_report.get("run_sha256", {}).get(condition_id) != _sha256(run_path):
            external_v3_failures.append(
                {"condition": condition_id, "reason": "run_hash"}
            )
    audit.add(
        "external_schema_constrained_population",
        external_v3_report.get("status") == "completed" and not external_v3_failures,
        "The token-level schema ablation shares the frozen 50-request population, hidden gold, strict validation, and hash-matched traces.",
        {
            "condition_count": len(external_v3_report.get("conditions", {})),
            "failures": external_v3_failures,
        },
    )

    external_v3_task_root = external_v3_root / "task_aware_quality_v1"
    external_v3_task_report = _load_json(external_v3_task_root / "report.json")
    external_v3_task_failures = []
    if set(external_v3_task_report.get("conditions", {})) != expected_external_v3_conditions:
        external_v3_task_failures.append({"reason": "condition_set"})
    for condition_id in sorted(expected_external_v3_conditions):
        rows_path = external_v3_task_root / condition_id / "task_quality_rows.jsonl"
        rows = _rows(rows_path)
        row_ids = _ids(rows, "id")
        if len(row_ids) != 50 or len(set(row_ids)) != 50 or set(row_ids) != set(e2e_gold_ids):
            external_v3_task_failures.append(
                {"condition": condition_id, "reason": "population"}
            )
        condition = external_v3_task_report.get("conditions", {}).get(condition_id, {})
        if condition.get("rows_sha256") != _sha256(rows_path):
            external_v3_task_failures.append(
                {"condition": condition_id, "reason": "rows_hash"}
            )
    schema_ablation_report = _load_json(
        external_v3_root / "schema_ablation_v1/task_aware_quality_v1/report.json"
    )
    expected_schema_ablation_conditions = {
        "deepseek_vl2_small_toolspec",
        schema_condition,
    }
    if (
        schema_ablation_report.get("status") != "completed"
        or set(schema_ablation_report.get("conditions", {}))
        != expected_schema_ablation_conditions
        or schema_ablation_report.get("reference_condition") != schema_condition
        or "deepseek_vl2_small_toolspec"
        not in schema_ablation_report.get("paired_comparisons_by_baseline", {})
    ):
        external_v3_task_failures.append({"reason": "schema_ablation_pairing"})
    audit.add(
        "external_schema_task_aware_quality_population",
        external_v3_task_report.get("status") == "completed"
        and not external_v3_task_failures,
        "Schema-constrained task-aware quality and its paired unconstrained ablation cover the complete frozen population.",
        {
            "condition_count": len(external_v3_task_report.get("conditions", {})),
            "failures": external_v3_task_failures,
        },
    )

    oracle_root = project_root / "runs/hydro_remote_agent/oracle_gold_routing_v1"
    oracle_report = _load_json(oracle_root / "comparison_report.json")
    oracle_run_path = oracle_root / "oracle_gold_routing/run_50.jsonl"
    oracle_rows = _rows(oracle_run_path)
    oracle_failures = []
    expected_oracle_conditions = expected_external_conditions | {"oracle_gold_routing"}
    if set(oracle_report.get("conditions", {})) != expected_oracle_conditions:
        oracle_failures.append({"reason": "condition_set"})
    oracle_ids = _ids(oracle_rows, "id")
    if len(oracle_ids) != 50 or len(set(oracle_ids)) != 50 or set(oracle_ids) != set(e2e_gold_ids):
        oracle_failures.append({"reason": "population"})
    if oracle_report.get("run_sha256", {}).get("oracle_gold_routing") != _sha256(oracle_run_path):
        oracle_failures.append({"reason": "run_hash"})
    gold_requests = {
        extract_gold(row)[0]: extract_gold(row)[1]
        for row in _rows(e2e_gold_path)
    }
    for row in oracle_rows:
        request_id = str(row.get("id", ""))
        try:
            prediction = parse_json_response(row.get("prediction"))
        except Exception:
            oracle_failures.append({"request_id": request_id, "reason": "prediction_parse"})
            continue
        if canonical_json(prediction) != canonical_json(gold_requests.get(request_id, {})):
            oracle_failures.append({"request_id": request_id, "reason": "not_gold_request"})
        if row.get("execution", {}).get("status") != "succeeded":
            oracle_failures.append({"request_id": request_id, "reason": "execution_status"})
        oracle_metadata = row.get("oracle", {})
        if (
            oracle_metadata.get("planner_executed") is not False
            or oracle_metadata.get("claim_scope") != "gold_policy_execution_reference"
            or row.get("timing", {}).get("planner_ms") != 0.0
        ):
            oracle_failures.append({"request_id": request_id, "reason": "oracle_provenance"})
    audit.add(
        "oracle_gold_routing_population",
        oracle_report.get("status") == "completed" and not oracle_failures,
        "Gold-policy reference executes all 50 frozen AgentRequests without a planner and preserves exact routing provenance.",
        {"condition_count": len(oracle_report.get("conditions", {})), "failures": oracle_failures},
    )

    oracle_task_root = oracle_root / "task_aware_quality_v1"
    oracle_task_report = _load_json(oracle_task_root / "report.json")
    oracle_task_failures = []
    if set(oracle_task_report.get("conditions", {})) != expected_oracle_conditions:
        oracle_task_failures.append({"reason": "condition_set"})
    for condition_id in sorted(expected_oracle_conditions):
        rows_path = oracle_task_root / condition_id / "task_quality_rows.jsonl"
        rows = _rows(rows_path)
        row_ids = _ids(rows, "id")
        if len(row_ids) != 50 or len(set(row_ids)) != 50 or set(row_ids) != set(e2e_gold_ids):
            oracle_task_failures.append({"condition": condition_id, "reason": "population"})
        condition = oracle_task_report.get("conditions", {}).get(condition_id, {})
        if condition.get("rows_sha256") != _sha256(rows_path):
            oracle_task_failures.append({"condition": condition_id, "reason": "rows_hash"})
    audit.add(
        "oracle_task_aware_quality_population",
        oracle_task_report.get("status") == "completed" and not oracle_task_failures,
        "Gold-policy task-aware report covers all four frozen conditions with hash-matched per-request scores.",
        {"condition_count": len(oracle_task_report.get("conditions", {})), "failures": oracle_task_failures},
    )

    return {
        "schema_version": "vague_hydro.mechanical_integrity_audit.v1",
        "status": audit.status,
        "checks": audit.checks,
        "summary": {
            "pass": sum(check["status"] == "pass" for check in audit.checks),
            "warn": sum(check["status"] == "warn" for check in audit.checks),
            "fail": sum(check["status"] == "fail" for check in audit.checks),
        },
    }


def _write_markdown(report: Mapping[str, Any], path: Path) -> None:
    lines = [
        "# Mechanical Experiment Integrity Audit",
        "",
        f"Overall status: **{str(report['status']).upper()}**",
        "",
        "| Check | Status | Details |",
        "|---|---|---|",
    ]
    for check in report["checks"]:
        details = str(check["details"]).replace("|", "\\|")
        lines.append(f"| `{check['id']}` | {str(check['status']).upper()} | {details} |")
    lines.extend(
        [
            "",
            "This report contains deterministic file, hash, count, lineage, and metric-recomputation checks.",
            "Research-claim judgment is recorded separately by the independent reviewer audit.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit VagueHydro experiment files mechanically.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--protocol", type=Path, default=Path("hydro_remote_agent/configs/experiment_protocol_v1.json"))
    parser.add_argument("--ledger", type=Path, default=Path("runs/hydro_remote_agent/experiments_v1/experiment_ledger.json"))
    parser.add_argument("--split-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("runs/hydro_remote_agent/integrity_audit_v1"))
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.resolve()
    protocol = args.protocol if args.protocol.is_absolute() else project_root / args.protocol
    ledger = args.ledger if args.ledger.is_absolute() else project_root / args.ledger
    output_dir = args.output_dir if args.output_dir.is_absolute() else project_root / args.output_dir
    report = run_audit(project_root, protocol, ledger, args.split_root.resolve())
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "mechanical_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_markdown(report, output_dir / "MECHANICAL_AUDIT.md")
    print(f"VAGUE_HYDRO_INTEGRITY_AUDIT status={report['status']} checks={report['summary']}")
    return 0 if report["status"] != "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())
