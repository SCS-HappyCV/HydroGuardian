import numpy as np

from hydro_remote_agent.tools.evaluate_cmge_capability_selector import evaluate_selector


def _row(index, region, target, baseline, candidate, baseline_points, candidate_points):
    return {
        "id": f"r{index}",
        "compound_id": f"c{index}",
        "sample_id": f"{region}_{index:06d}",
        "region": region,
        "intent": "class_segmentation",
        "target_class_id": target,
        "reference_class_id": -1,
        "operation": "none",
        "baseline_iou": baseline,
        "candidate_iou": candidate,
        "baseline_predicted_points": baseline_points,
        "candidate_predicted_points": candidate_points,
        "delta": candidate - baseline,
    }


def test_selector_uses_only_training_regions_and_reports_oracle_bound():
    rows = [
        _row(1, "00", 1, 0.2, 0.8, 100, 500),
        _row(2, "00", 2, 0.8, 0.2, 500, 100),
        _row(3, "01", 1, 0.3, 0.7, 120, 480),
        _row(4, "01", 2, 0.7, 0.3, 480, 120),
        _row(5, "02", 1, 0.2, 0.9, 100, 600),
        _row(6, "02", 2, 0.9, 0.1, 600, 100),
    ]

    report = evaluate_selector(rows, ["00", "01"], ["02"], alpha=1.0)

    assert report["train_count"] == 4
    assert report["test_count"] == 2
    assert report["selectors"]["oracle"]["selected_macro_iou"] == 0.9
    assert report["selectors"]["fixed_baseline"]["selected_macro_iou"] == 0.55
    assert report["selectors"]["dual_observation_ridge"]["selected_macro_iou"] >= 0.55
    assert len(report["decisions"]) == 2


def test_selector_metrics_are_finite_for_unseen_category():
    rows = [
        _row(1, "00", 1, 0.4, 0.5, 10, 12),
        _row(2, "01", 1, 0.5, 0.4, 12, 10),
        _row(3, "02", 99, 0.6, 0.3, 15, 5),
    ]

    report = evaluate_selector(rows, ["00", "01"], ["02"])

    for selector in report["selectors"].values():
        assert np.isfinite(selector["selected_macro_iou"])
