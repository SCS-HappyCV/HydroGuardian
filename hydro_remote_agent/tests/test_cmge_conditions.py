import json
from pathlib import Path

from hydro_remote_agent.tools.build_cmge_conditions import (
    build_conditions,
    read_jsonl,
    write_manifest,
)


DATA_PATH = (
    Path(__file__).parents[1].parent
    / "runs"
    / "cmge_pilot_v1"
    / "frozen240"
    / "compound_requests.jsonl"
)


def test_build_conditions_preserves_compounds_and_expands_claimwise_rows():
    compounds = read_jsonl(DATA_PATH)[:4]
    conditions = build_conditions(compounds)

    assert len(conditions["direct_only"]) == 4
    assert len(conditions["dense_only"]) == 4
    assert len(conditions["claimwise_rule_decomposition"]) == 8
    assert {row["id"] for row in conditions["claimwise_rule_decomposition"]} == {
        f"{compound['compound_id']}:claim{index}"
        for compound in compounds
        for index in (0, 1)
    }
    assert all(
        row["prediction"]["request_id"] == row["id"]
        for row in conditions["claimwise_rule_decomposition"]
    )


def test_baseline_rows_use_compound_id_but_keep_claim_metadata():
    compound = read_jsonl(DATA_PATH)[0]
    conditions = build_conditions([compound])

    direct = conditions["direct_only"][0]
    dense = conditions["dense_only"][0]
    assert direct["id"] == compound["compound_id"]
    assert dense["id"] == compound["compound_id"]
    assert direct["prediction"]["request_id"] == compound["compound_id"]
    assert dense["prediction"]["request_id"] == compound["compound_id"]
    assert direct["claim_index"] == 0
    assert dense["claim_index"] == 1


def test_manifest_is_jsonl(tmp_path: Path):
    compound = read_jsonl(DATA_PATH)[0]
    output = tmp_path / "compound_manifest.jsonl"
    write_manifest(output, [compound])
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["compound_id"] == compound["compound_id"]
    assert payload["query"] == compound["query"]
    assert payload["language"] == compound["language"]
    assert [claim["claim_index"] for claim in payload["claims"]] == [0, 1]


def test_asset_root_rewrites_nested_gold_paths():
    compound = read_jsonl(DATA_PATH)[0]
    conditions = build_conditions(
        [compound],
        asset_root="/workspace/HydroGuardian/benchmark/10M",
    )
    request = conditions["dense_only"][0]["prediction"]
    assert "/workspace/HydroGuardian/benchmark/10M/" in json.dumps(request)
    assert "/202221633069/" not in json.dumps(request)
