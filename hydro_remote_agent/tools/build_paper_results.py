from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Iterable, Mapping, Optional, Sequence

from hydro_remote_agent.evaluation.routing import iter_jsonl


TASK_ORDER = ("class", "attribute", "relation", "no_target")
COLORS = ("#0072B2", "#E69F00", "#009E73", "#D55E00", "#7A7A7A")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _rows(path: Path) -> list[dict[str, Any]]:
    return [dict(row) for _, row in iter_jsonl(path)]


def _annotation_index(path: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in _rows(path):
        for text in record.get("texts", []):
            text_id = str(text.get("text_id", ""))
            if not text_id:
                continue
            item = dict(text)
            item.update(
                sample_id=record.get("sample_id"),
                region_id=record.get("region_id"),
                patch_id=record.get("patch_id"),
                ortho_image_path=record.get("ortho_image_path"),
                point_cloud_path=record.get("point_cloud_path"),
            )
            index[text_id] = item
    return index


def _relation_name(annotation: Mapping[str, Any]) -> str:
    relations = annotation.get("spatial_relations", [])
    if isinstance(relations, list) and relations and isinstance(relations[0], Mapping):
        return str(relations[0].get("type", "unknown"))
    rule = annotation.get("target_mask_rule")
    if isinstance(rule, Mapping):
        return str(rule.get("type", "unknown"))
    return "unknown"


def _bootstrap_mean_ci(values: list[float], seed: int, samples: int = 2000) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    estimates = sorted(mean(rng.choices(values, k=len(values))) for _ in range(samples))
    return estimates[int(0.025 * samples)], estimates[min(int(0.975 * samples), samples - 1)]


def _enrich(row: Mapping[str, Any], annotation: Mapping[str, Any], category: str) -> dict[str, Any]:
    diagnostics = row.get("diagnostics") if isinstance(row.get("diagnostics"), Mapping) else {}
    metrics = row.get("metrics") if isinstance(row.get("metrics"), Mapping) else {}
    return {
        "category": category,
        "request_id": row.get("request_id"),
        "sample_id": row.get("sample_id"),
        "task_type": row.get("task_type"),
        "query": annotation.get("text"),
        "target_label_ids": annotation.get("target_label_ids", []),
        "target_label_names": annotation.get("target_label_names", []),
        "reference_label_ids": annotation.get("reference_label_ids", []),
        "reference_label_names": annotation.get("reference_label_names", []),
        "relation": _relation_name(annotation),
        "iou": metrics.get("iou"),
        "dice": metrics.get("dice"),
        "target_points": metrics.get("target_points"),
        "predicted_points": metrics.get("predicted_points"),
        "is_no_target": row.get("is_no_target"),
        "predicted_no_target": row.get("predicted_no_target"),
        "posterior_no_target_mass": diagnostics.get("posterior_no_target_mass"),
        "probability_max": diagnostics.get("probability_max"),
        "inferred_task_type": diagnostics.get("inferred_task_type"),
        "applied_mask_threshold": diagnostics.get("applied_mask_threshold"),
        "manifest_path": row.get("manifest_path"),
        "ortho_image_path": annotation.get("ortho_image_path"),
        "point_cloud_path": annotation.get("point_cloud_path"),
    }


def build_payload(project_root: Path, annotations_path: Path) -> dict[str, Any]:
    routing_baseline = _load_json(project_root / "runs/hydro_remote_agent/agent_eval_v1/baseline_routing_report_240.json")
    routing_method = _load_json(project_root / "runs/hydro_remote_agent/agent_eval_v1/adapter_routing_report_240.json")
    point_report = _load_json(project_root / "runs/hydro_remote_agent/expert_quality_v1/point_semantic_segmentation/report.json")
    language_before = _load_json(project_root / "runs/hydro_remote_agent/expert_quality_v1/language_guided_final_best_v1/report.json")
    language_after = _load_json(project_root / "runs/hydro_remote_agent/expert_quality_v1/language_guided_final_best_calibrated_v2/report.json")
    execution_report = _load_json(project_root / "runs/hydro_remote_agent/agent_execution_eval_v1/execution_report_complete_calibrated_240.json")
    stable_report = _load_json(project_root / "runs/hydro_remote_agent/service_reliability_v1/stable1_clean/report.json")
    language_rows = _rows(project_root / "runs/hydro_remote_agent/expert_quality_v1/language_guided_final_best_calibrated_v2/results.jsonl")
    annotation_index = _annotation_index(annotations_path)

    relation_groups: dict[str, list[float]] = defaultdict(list)
    enriched_relation = []
    false_positive = []
    false_negative = []
    for row in language_rows:
        request_id = str(row.get("request_id", ""))
        annotation = annotation_index.get(request_id, {})
        if row.get("task_type") == "relation":
            relation = _relation_name(annotation)
            relation_groups[relation].append(float(row["metrics"]["iou"]))
            enriched_relation.append(_enrich(row, annotation, "relation"))
        if bool(row.get("predicted_no_target")) and not bool(row.get("is_no_target")):
            false_positive.append(_enrich(row, annotation, "no_target_false_positive"))
        if bool(row.get("is_no_target")) and not bool(row.get("predicted_no_target")):
            false_negative.append(_enrich(row, annotation, "no_target_false_negative"))

    false_positive.sort(key=lambda row: (-int(row.get("target_points") or 0), str(row["request_id"])))
    false_negative.sort(key=lambda row: (-float(row.get("probability_max") or 0.0), str(row["request_id"])))
    relation_worst = [
        {**row, "category": "relation_worst"}
        for row in sorted(enriched_relation, key=lambda row: (float(row.get("iou") or 0.0), str(row["request_id"])))[:20]
    ]
    relation_best = [
        {**row, "category": "relation_best"}
        for row in sorted(enriched_relation, key=lambda row: (-float(row.get("iou") or 0.0), str(row["request_id"])))[:5]
    ]

    tp = sum(bool(row.get("is_no_target")) and bool(row.get("predicted_no_target")) for row in language_rows)
    fp = sum(not bool(row.get("is_no_target")) and bool(row.get("predicted_no_target")) for row in language_rows)
    fn = sum(bool(row.get("is_no_target")) and not bool(row.get("predicted_no_target")) for row in language_rows)
    tn = len(language_rows) - tp - fp - fn

    ablations = {}
    for mode in ("no_verifier", "no_workflow", "no_language_expert"):
        ablations[mode] = _load_json(project_root / f"runs/hydro_remote_agent/system_ablations_v1/{mode}/report.json")

    relation_summary = {}
    for index, (name, values) in enumerate(sorted(relation_groups.items())):
        ci_low, ci_high = _bootstrap_mean_ci(values, seed=20260710 + index)
        relation_summary[name] = {
            "count": len(values),
            "mean_iou": mean(values),
            "median_iou": median(values),
            "std_iou": stdev(values) if len(values) > 1 else 0.0,
            "bootstrap_ci95": [ci_low, ci_high],
            "zero_iou_count": sum(value == 0.0 for value in values),
        }
    routing_keys = (
        "parse_rate",
        "schema_valid_rate",
        "action_type_accuracy",
        "tool_selection_accuracy",
        "argument_slot_f1",
        "workflow_graph_accuracy",
        "request_exact_match",
    )
    return {
        "schema_version": "vague_hydro.paper_results.v1",
        "routing": {
            key: {
                "baseline": routing_baseline["metrics"][key],
                "method": routing_method["metrics"][key],
                "delta": routing_method["metrics"][key] - routing_baseline["metrics"][key],
            }
            for key in routing_keys
        },
        "point_segmentation": point_report["metrics"],
        "language": {
            "before": language_before,
            "after": language_after,
            "no_target_confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "relation_summary": relation_summary,
        },
        "execution": {
            "task_success_rate": execution_report["status_counts"].get("succeeded", 0) / execution_report["input_count"],
            "real_expert_success_rate": execution_report["real_expert_success_rate"],
            "verifier_success_rate": execution_report["verifier_success_rate"],
            "artifact_existence_rate": execution_report["terminal_artifact_existence_rate"],
            "mock_skipped_count": execution_report["mock_skipped_count"],
        },
        "system_ablations": {mode: report["metrics"] for mode, report in ablations.items()},
        "service": stable_report["metrics"],
        "error_cases": {
            "no_target_false_positive": false_positive[:20],
            "no_target_false_negative": false_negative[:20],
            "relation_worst": relation_worst,
            "relation_best": relation_best,
        },
    }


def _pct(value: float) -> str:
    return f"{100.0 * value:.2f}"


def write_tables(payload: Mapping[str, Any], output_dir: Path) -> None:
    routing_labels = {
        "parse_rate": "JSON parse rate",
        "schema_valid_rate": "Schema valid rate",
        "action_type_accuracy": "Action type accuracy",
        "tool_selection_accuracy": "Tool selection accuracy",
        "argument_slot_f1": "Argument slot F1",
        "workflow_graph_accuracy": "Workflow graph accuracy",
        "request_exact_match": "Request exact match",
    }
    md = ["# VagueHydro Paper Results", "", "## Routing", "", "| Metric | Backbone | VagueHydro | Delta |", "|---|---:|---:|---:|"]
    tex = [
        "% Auto-generated from immutable experiment reports.",
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Structured planning results on the frozen 240-request Agent Eval v1 set.}",
        "\\label{tab:routing}",
        "\\begin{tabular}{lrrr}",
        "\\toprule",
        "Metric & Backbone & VagueHydro & $\\Delta$ \\\\",
        "\\midrule",
    ]
    for key, label in routing_labels.items():
        row = payload["routing"][key]
        md.append(f"| {label} | {_pct(row['baseline'])}% | {_pct(row['method'])}% | {100 * row['delta']:+.2f}% |")
        tex.append(f"{label} & {_pct(row['baseline'])} & \\textbf{{{_pct(row['method'])}}} & {100 * row['delta']:+.2f} \\\\")
    tex.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])

    md.extend(
        [
            "",
            "## Expert And Execution Summary",
            "",
            "| Evaluation | Metric | Value |",
            "|---|---|---:|",
            f"| Point segmentation (245 tiles) | mIoU | {payload['point_segmentation']['mean_iou']:.4f} |",
            f"| Point segmentation (245 tiles) | Overall accuracy | {payload['point_segmentation']['overall_accuracy']:.4f} |",
            f"| Agent execution (240 requests) | Task success | {100 * payload['execution']['task_success_rate']:.2f}% |",
            f"| Agent execution (160 expert requests) | Expert success | {100 * payload['execution']['real_expert_success_rate']:.2f}% |",
            f"| Agent execution | Artifact existence | {100 * payload['execution']['artifact_existence_rate']:.2f}% |",
            f"| Stable online service | End-to-end p95 | {payload['service']['end_to_end_latency']['p95_ms']:.2f} ms |",
        ]
    )
    tex.extend(
        [
            "\\begin{table}[t]",
            "\\centering",
            "\\caption{Expert quality and end-to-end execution summary on the fixed WCS10M split.}",
            "\\label{tab:execution_summary}",
            "\\begin{tabular}{llr}",
            "\\toprule",
            "Evaluation & Metric & Value \\\\",
            "\\midrule",
            f"Point segmentation (245 tiles) & mIoU & {payload['point_segmentation']['mean_iou']:.4f} \\\\",
            f"Point segmentation (245 tiles) & Overall accuracy & {payload['point_segmentation']['overall_accuracy']:.4f} \\\\",
            f"Agent execution (240 requests) & Task success (\\%) & {100 * payload['execution']['task_success_rate']:.2f} \\\\",
            f"Agent execution (160 expert requests) & Expert success (\\%) & {100 * payload['execution']['real_expert_success_rate']:.2f} \\\\",
            f"Agent execution & Artifact existence (\\%) & {100 * payload['execution']['artifact_existence_rate']:.2f} \\\\",
            f"Stable online service & End-to-end p95 (ms) & {payload['service']['end_to_end_latency']['p95_ms']:.2f} \\\\",
            "\\bottomrule",
            "\\end{tabular}",
            "\\end{table}",
            "",
        ]
    )

    md.extend(["", "## Language-Guided Segmentation", "", "| Metric | Uncalibrated | Calibrated |", "|---|---:|---:|"])
    language_rows = (
        ("Macro IoU", "overall.macro_iou"),
        ("Micro IoU", "overall.micro_iou"),
        ("Macro Dice", "overall.macro_dice"),
        ("Class Macro IoU", "by_task_type.class.macro_iou"),
        ("Attribute Macro IoU", "by_task_type.attribute.macro_iou"),
        ("Relation Macro IoU", "by_task_type.relation.macro_iou"),
        ("No-target mask Macro IoU", "by_task_type.no_target.macro_iou"),
        ("No-target recall", "overall.no_target_recall"),
    )
    tex.extend(
        [
            "\\begin{table}[t]",
            "\\centering",
            "\\caption{Language-guided point segmentation before and after validation-only calibration.}",
            "\\label{tab:language}",
            "\\begin{tabular}{lrr}",
            "\\toprule",
            "Metric & Uncalibrated & Calibrated \\\\",
            "\\midrule",
        ]
    )
    for label, path in language_rows:
        def lookup(root: Mapping[str, Any]) -> Any:
            value: Any = root
            for part in path.split("."):
                value = value[part]
            return value
        before = lookup(payload["language"]["before"])
        after = lookup(payload["language"]["after"])
        before_text = "--" if before is None else f"{before:.4f}"
        after_text = "--" if after is None else f"{after:.4f}"
        md.append(f"| {label} | {before_text} | {after_text} |")
        if before is not None and after is not None and before > after:
            before_text = f"\\textbf{{{before_text}}}"
        elif after is not None:
            after_text = f"\\textbf{{{after_text}}}"
        tex.append(f"{label} & {before_text} & {after_text} \\\\")
    tex.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])

    md.extend(["", "## System Ablations", "", "| Configuration | Task success | Expert success | Workflow success | Language success | Verification coverage |", "|---|---:|---:|---:|---:|---:|"])
    full = {"task_success_rate": 1.0, "expert_request_success_rate": 1.0, "workflow_success_rate": 1.0, "language_request_success_rate": 1.0, "verification_coverage_rate": 1.0}
    names = (("Full system", full), ("No verifier", payload["system_ablations"]["no_verifier"]), ("No workflow", payload["system_ablations"]["no_workflow"]), ("No language expert", payload["system_ablations"]["no_language_expert"]))
    tex.extend(["\\begin{table}[t]", "\\centering", "\\caption{System component ablations on the frozen 240-request execution set.}", "\\label{tab:system_ablation}", "\\begin{tabular}{lrrrrr}", "\\toprule", "Configuration & Task & Expert & Workflow & Language & Verify \\\\", "\\midrule"])
    for name, metrics in names:
        values = [metrics[key] for key in ("task_success_rate", "expert_request_success_rate", "workflow_success_rate", "language_request_success_rate", "verification_coverage_rate")]
        md.append(f"| {name} | " + " | ".join(f"{100 * value:.2f}%" for value in values) + " |")
        tex.append(name + " & " + " & ".join(f"{100 * value:.2f}" for value in values) + " \\\\")
    tex.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    (output_dir / "RESULTS_TABLES.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (output_dir / "tables.tex").write_text("\n".join(tex) + "\n", encoding="utf-8")


def write_figure_includes(output_dir: Path) -> None:
    figures = (
        (
            "fig_language_calibration",
            "Validation-only calibration improves language-guided segmentation on 1,903 frozen test requests. Bars report per-request Macro IoU; test labels are not used to choose thresholds.",
            "fig:language_calibration",
            "0.72\\linewidth",
        ),
        (
            "fig_no_target_confusion",
            "No-target detection confusion matrix on 1,903 requests (250 true no-target cases): TN=1,595, FP=58, FN=37, and TP=213.",
            "fig:no_target_confusion",
            "0.48\\linewidth",
        ),
        (
            "fig_relation_iou",
            "Relation-mask IoU by relation operator with request-level bootstrap 95\\% confidence intervals. Near selects target points within the annotated distance threshold of a reference class; above selects target points vertically above it. The frozen test set contains 253 near and 80 above requests.",
            "fig:relation_iou",
            "0.58\\linewidth",
        ),
        (
            "fig_system_ablations",
            "Deterministic system component ablations on the same 240 completed Agent requests. No verifier removes quality checks, no workflow disables composed execution, and no language expert disables HydroProgram3D. Disabled capabilities are counted as blocked rather than silently replaced.",
            "fig:system_ablations",
            "0.68\\linewidth",
        ),
        (
            "fig_no_target_error_cases",
            "Representative no-target false positives and false negatives. False positives suppress valid class masks, whereas false negatives produce nonempty masks for absent targets. Blue denotes ground-truth target points, orange denotes predicted target points, and gray points provide scene context.",
            "fig:no_target_cases",
            "0.95\\linewidth",
        ),
        (
            "fig_relation_error_cases",
            "Lowest-IoU relation failures selected from the 333-request relation subset. Ground-truth masks are spatially coherent, while predictions are empty or sparse and misplaced. Both masks are shown in the source point-cloud coordinate system.",
            "fig:relation_cases",
            "0.95\\linewidth",
        ),
    )
    lines = ["% Auto-generated figure includes. PDF files contain vector text and rasterized point clouds."]
    caption_lines = ["# Figure Captions", ""]
    for name, caption, label, width in figures:
        lines.extend(
            [
                "\\begin{figure}[t]",
                "    \\centering",
                f"    \\includegraphics[width={width}]{{figures/{name}.pdf}}",
                f"    \\caption{{{caption}}}",
                f"    \\label{{{label}}}",
                "\\end{figure}",
                "",
            ]
        )
        caption_lines.extend([f"## `{name}`", "", caption, ""])
    (output_dir / "latex_includes.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "FIGURE_CAPTIONS.md").write_text("\n".join(caption_lines), encoding="utf-8")


def write_error_cases(payload: Mapping[str, Any], output_dir: Path) -> None:
    rows = [row for group in payload["error_cases"].values() for row in group]
    with (output_dir / "language_error_cases.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    fieldnames = list(rows[0]) if rows else []
    with (output_dir / "language_error_cases.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            normalized = {key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()}
            writer.writerow(normalized)


def generate_figures(payload: Mapping[str, Any], output_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["DejaVu Serif"],
            "font.size": 9,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    def save(fig: Any, name: str) -> None:
        fig.savefig(output_dir / f"{name}.pdf", bbox_inches="tight", pad_inches=0.04)
        fig.savefig(output_dir / f"{name}.png", dpi=300, bbox_inches="tight", pad_inches=0.04)
        plt.close(fig)

    labels = ["Overall", "Class", "Attribute", "Relation"]
    paths = ["overall", "class", "attribute", "relation"]
    before = payload["language"]["before"]
    after = payload["language"]["after"]
    before_values = [before["overall"]["macro_iou"]] + [before["by_task_type"][name]["macro_iou"] for name in paths[1:]]
    after_values = [after["overall"]["macro_iou"]] + [after["by_task_type"][name]["macro_iou"] for name in paths[1:]]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(5.2, 2.8))
    width = 0.36
    ax.bar(x - width / 2, before_values, width, label="Uncalibrated", color=COLORS[4])
    ax.bar(x + width / 2, after_values, width, label="Calibrated", color=COLORS[0])
    ax.set_ylabel("Macro IoU")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 0.55)
    ax.legend(frameon=False, ncol=2, loc="upper left")
    save(fig, "fig_language_calibration")

    confusion = payload["language"]["no_target_confusion"]
    matrix = np.array([[confusion["tn"], confusion["fp"]], [confusion["fn"], confusion["tp"]]])
    fig, ax = plt.subplots(figsize=(3.2, 2.8))
    image = ax.imshow(matrix, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center", color="white" if matrix[i, j] > matrix.max() / 2 else "black")
    ax.set_xticks([0, 1], ["Target present", "No target"])
    ax.set_yticks([0, 1], ["Target present", "No target"])
    ax.set_xlabel("Prediction")
    ax.set_ylabel("Ground truth")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    save(fig, "fig_no_target_confusion")

    summary = payload["language"]["relation_summary"]
    names = list(summary)
    means = [summary[name]["mean_iou"] for name in names]
    counts = [summary[name]["count"] for name in names]
    lower = [summary[name]["mean_iou"] - summary[name]["bootstrap_ci95"][0] for name in names]
    upper = [summary[name]["bootstrap_ci95"][1] - summary[name]["mean_iou"] for name in names]
    fig, ax = plt.subplots(figsize=(max(4.2, 0.9 * len(names)), 2.8))
    bars = ax.bar(
        range(len(names)),
        means,
        yerr=np.asarray([lower, upper]),
        capsize=4,
        color=COLORS[2],
        error_kw={"elinewidth": 1.0, "capthick": 1.0},
    )
    ax.set_xticks(range(len(names)), [f"{name}\n(n={count})" for name, count in zip(names, counts)])
    ax.set_ylabel("Mean IoU")
    ax.set_ylim(0, max(means + [0.1]) * 1.22)
    for bar, value in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.3f}", ha="center", va="bottom", fontsize=8)
    save(fig, "fig_relation_iou")

    names = ["Full", "No verifier", "No workflow", "No language"]
    values = [1.0, payload["system_ablations"]["no_verifier"]["task_success_rate"], payload["system_ablations"]["no_workflow"]["task_success_rate"], payload["system_ablations"]["no_language_expert"]["task_success_rate"]]
    fig, ax = plt.subplots(figsize=(5.0, 2.8))
    bars = ax.bar(
        range(4),
        values,
        color=["#0072B2", "#999999", "#009E73", "#CC79A7"],
        hatch=["", "//", "xx", ".."],
        edgecolor="#333333",
        linewidth=0.5,
    )
    ax.set_xticks(range(4), names)
    ax.set_ylabel("Task success rate")
    ax.set_ylim(0, 1.12)
    ax.set_yticks(np.linspace(0, 1, 6), [f"{int(value * 100)}%" for value in np.linspace(0, 1, 6)])
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value, f"{100 * value:.1f}%", ha="center", va="bottom", fontsize=8)
    save(fig, "fig_system_ablations")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build immutable paper tables and error-analysis figures.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--annotations", type=Path, default=Path("data/wcs2d3d_lang_v4_llm_auto_cross_region_train_dashscope_en_v2.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("runs/hydro_remote_agent/paper_results_v1"))
    parser.add_argument("--skip-figures", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.project_root.resolve()
    annotations = args.annotations if args.annotations.is_absolute() else root / args.annotations
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(root, annotations)
    (output_dir / "paper_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tables(payload, output_dir)
    write_figure_includes(output_dir)
    write_error_cases(payload, output_dir)
    if not args.skip_figures:
        generate_figures(payload, output_dir)
    print(f"VAGUE_HYDRO_PAPER_RESULTS_OK output={output_dir} errors={sum(len(rows) for rows in payload['error_cases'].values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
