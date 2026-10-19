from pathlib import Path

from hydro_remote_agent.tools.evaluate_cmge_conditions import evaluate


def test_evaluate_accepts_learned_claimwise_condition(tmp_path: Path):
    compounds = tmp_path / "compounds.jsonl"
    conditions = tmp_path / "conditions"
    learned = conditions / "learned_claimwise"
    learned.mkdir(parents=True)
    compounds.write_text("", encoding="utf-8")
    (learned / "predictions.jsonl").write_text("", encoding="utf-8")
    (learned / "execution.jsonl").write_text("", encoding="utf-8")

    report = evaluate(
        compounds,
        conditions,
        tmp_path,
        tmp_path / "report.json",
        ("learned_claimwise",),
    )

    assert set(report["conditions"]) == {"learned_claimwise"}
    assert report["conditions"]["learned_claimwise"]["compound_count"] == 0
