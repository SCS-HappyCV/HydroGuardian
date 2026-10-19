from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch
from transformers import LogitsProcessorList

from hydro_remote_agent.rewards.completion_adapter import adapt_completion
from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.rewards.structural_contrast_reward_v2 import StructuralContrastRewardV2
from hydro_remote_agent.schema_constrained_generation import AgentRequestPrefixParser, union_argument_properties
from hydro_remote_agent.schemas.agent_action import AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.train_vaguehydro_r_m2_grpo_smoke import SchemaConstrainedLogitsProcessor
from hydro_remote_agent.tools.vaguehydro_preference_pilot_core import ROOT, prompt_text, read_jsonl


def parser_factory(registry: Any, enforce_complete_validation: bool = True):
    argument_properties = union_argument_properties([tool.arguments_schema for tool in registry.tools])
    result_types = {value for tool in registry.tools for value in tool.output.result_types}
    coordinate_spaces = {tool.output.coordinate_space for tool in registry.tools}

    def validate(value: Mapping[str, Any]) -> bool:
        try:
            AgentRequest.from_dict(value, registry)
        except Exception:
            return False
        return True

    return lambda: AgentRequestPrefixParser(
        registry.names(),
        argument_properties,
        result_types,
        coordinate_spaces,
        validate if enforce_complete_validation else None,
    )


def mandatory_fragments(registry: Any) -> list[str]:
    argument_properties = union_argument_properties([tool.arguments_schema for tool in registry.tools])
    argument_enums = {
        str(value)
        for schema in argument_properties.values()
        for value in schema.get("enum", [])
        if isinstance(value, str)
    }
    return list({
        "{", "}", "[", "]", ":", ",", '"', "true", "false", "null",
        *AgentRequestPrefixParser.ROOT_KEYS, *AgentRequestPrefixParser.ACTION_KEYS,
        *AgentRequestPrefixParser.STEP_KEYS, *AgentRequestPrefixParser.EXPECTED_KEYS,
        *argument_properties.keys(), *argument_enums,
        *registry.names(), "1.0", "direct_answer", "tool_call", "workflow",
        "clarification", "abstain", "auto", "required", "skip",
        *(value for tool in registry.tools for value in tool.output.result_types),
        *(tool.output.coordinate_space for tool in registry.tools),
    })


def generate_rows(
    model: Any,
    tokenizer: Any,
    rows: Sequence[Mapping[str, Any]],
    cfg: Mapping[str, Any],
    constrained: bool,
) -> list[dict[str, Any]]:
    registry = load_tool_registry(ROOT / str(cfg["tool_registry"]))
    # Cross-field AgentRequest validation is not prefix-decomposable. Applying it
    # inside greedy token masking can create a dead end at the final root brace.
    # score_rows retains the full strict validation used for release decisions.
    make_parser = parser_factory(registry, enforce_complete_validation=False)
    mandatory = mandatory_fragments(registry)
    generation = cfg["generation"]
    output: list[dict[str, Any]] = []
    model.eval()
    for row in rows:
        text = prompt_text(tokenizer, row["prompt_messages"])
        inputs = tokenizer(text, return_tensors="pt", add_special_tokens=False).to("cuda")
        prompt_length = int(inputs["input_ids"].shape[1])
        processors = None
        constraint_processor = None
        if constrained:
            constraint_processor = SchemaConstrainedLogitsProcessor(
                tokenizer, tokenizer.eos_token_id, prompt_length, make_parser,
                int(generation["decoder_max_allowed_tokens"]),
                int(generation["decoder_scan_top_tokens"]), mandatory,
                exact_reparse=True,
            )
            processors = LogitsProcessorList([constraint_processor])
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                do_sample=bool(generation["do_sample"]),
                temperature=float(generation["temperature"]),
                top_p=float(generation["top_p"]),
                max_new_tokens=int(generation["max_new_tokens"]),
                logits_processor=processors,
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.pad_token_id,
                use_cache=True,
                disable_compile=True,
            )
        ids = generated[0, prompt_length:].detach().cpu().tolist()
        eos = tokenizer.eos_token_id in ids
        eos_index = ids.index(tokenizer.eos_token_id) if eos else None
        kept = ids[:eos_index] if eos_index is not None else ids
        completion = tokenizer.decode(kept, skip_special_tokens=True).strip()
        constraint_state = None
        if constraint_processor is not None:
            final_state = make_parser()
            final_state.feed(completion)
            constraint_state = final_state.result().to_dict()
        output.append({
            "id": row["id"], "completion": completion, "token_count": len(kept),
            "eos": eos, "clipped": not eos and len(kept) >= int(generation["max_new_tokens"]),
            "decoder_active": constrained, "constraint_state": constraint_state,
        })
    return output


def score_rows(generated: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]], cfg: Mapping[str, Any]):
    registry = load_tool_registry(ROOT / str(cfg["tool_registry"]))
    reward_a = GoldActionReward(registry, cfg["evaluation"]["reward_a_weights"])
    reward_b = StructuralContrastRewardV2(registry)
    source = {str(row["id"]): row for row in rows}
    details = []
    for result in generated:
        gold = source[str(result["id"])]["chosen"]
        adapted = adapt_completion(result["completion"])
        payload: Any = {}
        legal = False
        error = adapted.error
        if adapted.valid and adapted.payload is not None:
            payload = adapted.payload
            try:
                AgentRequest.from_dict(payload, registry)
                legal = True
                error = None
            except Exception as exc:
                error = str(exc)
        a = reward_a.score(payload, gold).to_dict()
        b = reward_b.score(payload, gold).to_dict()
        exact = legal and json.dumps(payload, sort_keys=True, separators=(",", ":")) == json.dumps(gold, sort_keys=True, separators=(",", ":"))
        details.append({**result, "strict_valid": legal, "error": error, "exact_match": exact, "reward_a": a, "reward_b": b})
    count = len(details)
    mean = lambda key, reward: sum(float(row[reward][key]) for row in details) / count
    metrics = {
        "count": count,
        "strict_legality_rate": sum(row["strict_valid"] for row in details) / count,
        "parse_rate": sum(adapt_completion(row["completion"]).valid for row in details) / count,
        "eos_rate": sum(row["eos"] for row in details) / count,
        "clipping_rate": sum(row["clipped"] for row in details) / count,
        "exact_match_rate": sum(row["exact_match"] for row in details) / count,
        "reward_a": {key: mean(key, "reward_a") for key in ("total", "schema", "action", "tool", "argument", "workflow", "stop")},
        "reward_b": {"total": mean("total", "reward_b")},
        "field_accuracy": sum(mean(key, "reward_a") for key in ("action", "tool", "argument", "workflow", "stop")) / 5.0,
    }
    return metrics, details


def load_eval(run_dir: Path, name: str) -> list[dict[str, Any]]:
    return read_jsonl(run_dir / name)
