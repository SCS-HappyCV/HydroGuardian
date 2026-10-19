import numpy as np

from hydro_remote_agent.tools.analyze_cmge_policy_ablation import (
    _bootstrap_difference,
    _mcnemar,
)


def test_bootstrap_paired_difference():
    result = _bootstrap_difference(
        np.asarray([.5, .8, .4]), np.asarray([.2, .3, .4]), 1000, 7
    )
    assert result["mean_difference"] > 0
    assert result["win_tie_loss"] == {"win": 2, "tie": 1, "loss": 0}


def test_mcnemar_counts_discordant_pairs():
    result = _mcnemar(
        np.asarray([True, True, False, True]),
        np.asarray([False, True, True, False]),
    )
    assert result["candidate_only_correct"] == 2
    assert result["baseline_only_correct"] == 1
    assert result["discordant_count"] == 3
