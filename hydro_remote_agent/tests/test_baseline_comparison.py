from hydro_remote_agent.evaluation.baseline_comparison import _mcnemar_exact, _paired_bootstrap


def test_paired_bootstrap_reports_candidate_minus_baseline() -> None:
    result = _paired_bootstrap([0, 0, 1, 1], [1, 1, 1, 1], samples=200, seed=7)
    assert result["delta"] == 0.5
    assert result["lower"] >= 0.0
    assert result["upper"] <= 1.0


def test_mcnemar_exact_counts_improvements_and_regressions() -> None:
    result = _mcnemar_exact([0, 0, 1, 1], [1, 1, 0, 1])
    assert result["improved"] == 2
    assert result["regressed"] == 1
    assert 0.0 <= result["p_value_two_sided"] <= 1.0
