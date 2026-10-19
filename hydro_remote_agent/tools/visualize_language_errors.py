from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from hydro_remote_agent.evaluation.routing import iter_jsonl


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return [dict(row) for _, row in iter_jsonl(path)]


def _annotation_index(path: Path) -> dict[str, dict[str, Any]]:
    index = {}
    for _, record in iter_jsonl(path):
        for text in record.get("texts", []):
            item = dict(text)
            item.update(region_id=record.get("region_id"), patch_id=record.get("patch_id"))
            index[str(text["text_id"])] = item
    return index


def _artifact_path(manifest: Mapping[str, Any], name: str) -> Path:
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, Mapping) and name in artifacts:
        return Path(str(artifacts[name]))
    result = manifest.get("result")
    if isinstance(result, Mapping):
        artifacts = result.get("artifacts")
        if isinstance(artifacts, Mapping) and name in artifacts:
            return Path(str(artifacts[name]))
    raise KeyError(f"Artifact {name!r} not found in manifest")


def _target_mask(points: Any, annotation: Mapping[str, Any]) -> np.ndarray:
    from wcs_unified.dataset import build_rule_target_mask

    labels = points[:, 6].long()
    rule = annotation.get("target_mask_rule")
    if isinstance(rule, Mapping):
        return build_rule_target_mask(points[:, :3], labels, dict(rule)).numpy().astype(bool)
    target = np.zeros(len(points), dtype=bool)
    if not bool(annotation.get("is_no_target", False)):
        label_values = labels.numpy()
        for label_id in annotation.get("target_label_ids", []):
            target |= label_values == int(label_id)
    return target


def _indices(target: np.ndarray, prediction: np.ndarray, limit: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    positive = np.flatnonzero(target | prediction)
    background = np.flatnonzero(~(target | prediction))
    positive_limit = min(len(positive), max(limit // 2, 1))
    if len(positive) > positive_limit:
        positive = np.sort(rng.choice(positive, positive_limit, replace=False))
    remaining = max(limit - len(positive), 0)
    if len(background) > remaining:
        background = np.sort(rng.choice(background, remaining, replace=False))
    return np.sort(np.concatenate([positive, background]))


def _load_case(case: Mapping[str, Any], annotation: Mapping[str, Any], data_root: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    from wcs_unified.dataset import load_point_tensor

    point_path = data_root / str(annotation["region_id"]) / "velodyne" / f"{annotation['patch_id']}.txt"
    points = load_point_tensor(str(point_path))
    target = _target_mask(points, annotation)
    manifest = json.loads(Path(str(case["manifest_path"])).read_text(encoding="utf-8"))
    with np.load(_artifact_path(manifest, "target_mask"), allow_pickle=False) as payload:
        prediction = np.asarray(payload["target_mask"], dtype=bool).reshape(-1)
    xyz = points[:, :3].numpy()
    if target.size != prediction.size or target.size != len(xyz):
        raise ValueError(f"Point-count mismatch for {case['request_id']}: {len(xyz)}, {target.size}, {prediction.size}")
    return xyz, target, prediction


def _plot_cases(cases: list[dict[str, Any]], annotations: Mapping[str, Mapping[str, Any]], data_root: Path, output_dir: Path, name: str, max_points: int) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not cases:
        return
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"], "font.size": 9, "pdf.fonttype": 42})
    fig, axes = plt.subplots(len(cases), 2, figsize=(7.2, 2.45 * len(cases)), squeeze=False)
    for row_index, case in enumerate(cases):
        annotation = annotations[str(case["request_id"])]
        xyz, target, prediction = _load_case(case, annotation, data_root)
        indices = _indices(target, prediction, max_points, seed=row_index + 17)
        x, y = xyz[indices, 0], xyz[indices, 1]
        for column, (mask, label) in enumerate(((target, "Ground truth"), (prediction, "Prediction"))):
            ax = axes[row_index, column]
            selected = mask[indices]
            ax.scatter(x[~selected], y[~selected], s=0.12, c="#C7C7C7", alpha=0.28, linewidths=0, rasterized=True)
            ax.scatter(x[selected], y[selected], s=1.0 if column else 0.55, c="#D55E00" if column else "#0072B2", alpha=0.95, linewidths=0, rasterized=True)
            ax.set_aspect("equal", adjustable="box")
            ax.set_axis_off()
            if row_index == 0:
                ax.set_title(label, fontsize=10, pad=3)
            if column == 1:
                positive = np.flatnonzero(selected)
                if len(positive):
                    px, py = x[positive], y[positive]
                    margin_x = max((px.max() - px.min()) * 0.08, 0.5)
                    margin_y = max((py.max() - py.min()) * 0.08, 0.5)
                    rectangle = plt.Rectangle(
                        (px.min() - margin_x, py.min() - margin_y),
                        px.max() - px.min() + 2 * margin_x,
                        py.max() - py.min() + 2 * margin_y,
                        fill=False,
                        edgecolor="#D55E00",
                        linewidth=0.9,
                    )
                    ax.add_patch(rectangle)
                    ax.text(0.98, 0.02, f"{int(prediction.sum()):,} predicted points", transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="#8C3B00")
                else:
                    ax.text(0.98, 0.02, "No predicted points", transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="#8C3B00")
            if column == 0:
                x_span = float(x.max() - x.min()) if len(x) else 0.0
                y_span = float(y.max() - y.min()) if len(y) else 0.0
                if x_span >= 12.0 and y_span > 0.0:
                    x0 = float(x.min() + 0.05 * x_span)
                    y0 = float(y.min() + 0.05 * y_span)
                    ax.plot([x0, x0 + 10.0], [y0, y0], color="#222222", linewidth=1.5)
                    ax.text(x0 + 5.0, y0 + 0.015 * y_span, "10 m", ha="center", va="bottom", fontsize=8)
        query = str(annotation.get("text", ""))
        if len(query) > 92:
            query = query[:89] + "..."
        descriptor = f"{case['category']} | IoU={float(case.get('iou') or 0.0):.3f} | {case['request_id']}"
        axes[row_index, 0].text(0.0, -0.08, descriptor + "\n" + query, transform=axes[row_index, 0].transAxes, ha="left", va="top", fontsize=8.5, clip_on=False)
    fig.subplots_adjust(left=0.02, right=0.99, top=0.97, bottom=0.03, hspace=0.43, wspace=0.03)
    fig.savefig(output_dir / f"{name}.pdf", bbox_inches="tight", pad_inches=0.04)
    fig.savefig(output_dir / f"{name}.png", dpi=300, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Visualize no-target and relation point-mask errors.")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cases-per-group", type=int, default=3)
    parser.add_argument("--max-points", type=int, default=30000)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cases_per_group < 1 or args.max_points < 100:
        raise ValueError("cases-per-group must be positive and max-points must be at least 100")
    cases = _load_cases(args.cases)
    annotations = _annotation_index(args.annotations)
    groups: dict[str, list[dict[str, Any]]] = {}
    for category in ("no_target_false_positive", "no_target_false_negative", "relation_worst"):
        groups[category] = [row for row in cases if row.get("category") == category][: args.cases_per_group]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _plot_cases(
        groups["no_target_false_positive"] + groups["no_target_false_negative"],
        annotations,
        args.data_root,
        args.output_dir,
        "fig_no_target_error_cases",
        args.max_points,
    )
    _plot_cases(groups["relation_worst"], annotations, args.data_root, args.output_dir, "fig_relation_error_cases", args.max_points)
    print(
        "VAGUE_HYDRO_ERROR_VIS_OK "
        f"no_target={len(groups['no_target_false_positive']) + len(groups['no_target_false_negative'])} "
        f"relation={len(groups['relation_worst'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
