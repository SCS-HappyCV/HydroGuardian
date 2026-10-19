from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import torch
from transformers import AutoTokenizer

from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.schema_constrained_generation import (
    AgentRequestPrefixParser,
    union_argument_properties,
)
from hydro_remote_agent.schemas.agent_action import AgentActionError, AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.train_vaguehydro_r_m2_grpo_smoke import SchemaConstrainedLogitsProcessor


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    run_dir = args.run_dir if args.run_dir.is_absolute() else root / args.run_dir
    freeze = read_json(run_dir / "CONFIG_FREEZE.json")
    registry = load_tool_registry(root / "hydro_remote_agent/configs/tool_registry.yaml")
    properties = union_argument_properties([tool.arguments_schema for tool in registry.tools])
    result_types = {value for tool in registry.tools for value in tool.output.result_types}
    coordinate_spaces = {tool.output.coordinate_space for tool in registry.tools}

    def validate(value: Mapping[str, Any]) -> bool:
        try:
            AgentRequest.from_dict(value, registry)
        except (AgentActionError, ValueError, TypeError):
            return False
        return True

    def factory() -> AgentRequestPrefixParser:
        return AgentRequestPrefixParser(
            registry.names(), properties, result_types, coordinate_spaces, validate
        )

    records = {}
    train_path = root / "hydro_remote_agent/data/vague_hydro_sft_v2/train_curriculum_16360.jsonl"
    requested = set(freeze["data"]["sample_ids"])
    with train_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if str(record.get("id")) in requested:
                assistant = next(message for message in reversed(record["messages"]) if message["role"] == "assistant")
                records[str(record["id"])] = json.loads(assistant["content"])
    tokenizer = AutoTokenizer.from_pretrained(freeze["base_model"], local_files_only=True)
    eos = int(tokenizer.eos_token_id)
    replay = []
    for sample_id in freeze["data"]["sample_ids"]:
        text = json.dumps(records[sample_id], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        token_ids = tokenizer.encode(text, add_special_tokens=False)
        prefix: list[int] = []
        all_allowed = True
        replay_state = factory()
        for token_id in token_ids:
            piece = tokenizer.decode([token_id], skip_special_tokens=False)
            if not replay_state.feed(piece):
                all_allowed = False
                break
            prefix.append(token_id)
        eos_scores = torch.zeros((1, len(tokenizer)))
        processor = SchemaConstrainedLogitsProcessor(
            tokenizer, eos, 0, factory, 1, 1, ["}"]
        )
        final_scores = processor(torch.tensor([prefix], dtype=torch.long), eos_scores)
        eos_only = torch.isfinite(final_scores[0]).nonzero().flatten().tolist() == [eos]
        replay.append(
            {
                "sample_id": sample_id,
                "token_count": len(token_ids),
                "all_gold_tokens_allowed": all_allowed,
                "eos_only_after_complete": eos_only,
            }
        )

    lexical_cases = []
    valid_text = json.dumps(records[freeze["data"]["sample_ids"][2]], ensure_ascii=False, separators=(",", ":"))
    cases = {
        "chinese_and_nested_agent_request": (valid_text, True, True),
        "unterminated_string": ('{"request_id":"中文', True, False),
        "illegal_field": ('{"forbidden"', False, False),
        "illegal_enum": ('{"intent":"not_an_intent', False, False),
    }
    for name, (text, expected_valid, expected_complete) in cases.items():
        state = factory()
        actual_valid = state.feed(text)
        result = state.result()
        passed = actual_valid == expected_valid and result.complete == expected_complete
        lexical_cases.append(
            {"name": name, "passed": passed, "state": result.to_dict()}
        )

    reward = GoldActionReward(registry, freeze["reward_weights"])
    gold = records[freeze["data"]["sample_ids"][0]]
    scored_candidates = [json.dumps(gold, ensure_ascii=False), '{"intent":"bad"']
    scored = [reward.score(value, gold).to_dict() for value in scored_candidates]
    retention_test = {
        "input_candidate_count": len(scored_candidates),
        "scored_candidate_count": len(scored),
        "invalid_candidate_retained": bool(scored[1]["invalid"]),
        "passed": len(scored_candidates) == len(scored) and bool(scored[1]["invalid"]),
    }
    passed = (
        all(item["passed"] for item in lexical_cases)
        and all(item["all_gold_tokens_allowed"] and item["eos_only_after_complete"] for item in replay)
        and retention_test["passed"]
    )
    report = {
        "schema_version": "vaguehydro_r.m4_constrained_decoder_test.v1",
        "status": "pass" if passed else "fail",
        "lexical_schema_cases": lexical_cases,
        "gold_token_replay": replay,
        "candidate_retention_and_scoring": retention_test,
        "implementation_sha256": sha256_file(root / "hydro_remote_agent/schema_constrained_generation.py"),
        "training_entry_sha256": sha256_file(root / "hydro_remote_agent/tools/train_vaguehydro_r_m2_grpo_smoke.py"),
        "posthoc_repair": False,
        "resample_until_success": False,
    }
    (run_dir / "CONSTRAINED_DECODER_TEST_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# Constrained Decoder Test Report", "",
        f"- Status: **{report['status'].upper()}**",
        f"- Lexical/schema cases passed: `{sum(item['passed'] for item in lexical_cases)}/{len(lexical_cases)}`",
        f"- Gold token replays passed: `{sum(item['all_gold_tokens_allowed'] and item['eos_only_after_complete'] for item in replay)}/{len(replay)}`",
        f"- Candidate retention/scoring: `{retention_test['passed']}`", "",
        "The test uses online token masking and EOS gating. It performs no post-hoc repair or success resampling.",
    ]
    (run_dir / "CONSTRAINED_DECODER_TEST_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report["status"])
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
