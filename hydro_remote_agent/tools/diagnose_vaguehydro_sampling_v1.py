"""Token-level A/B sampling diagnosis for the VagueHydro reward-fix path."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import torch
from peft import PeftModel
from transformers import AutoProcessor, LogitsProcessor, Qwen3VLForConditionalGeneration
from trl.data_utils import maybe_apply_chat_template, prepare_multimodal_messages

from hydro_remote_agent.backbones.qwen3_vl_planner import planner_system_prompt
from hydro_remote_agent.schema_constrained_generation import AgentRequestPrefixParser, union_argument_properties
from hydro_remote_agent.schemas.agent_action import AgentActionError, AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
def user_content(record: dict[str, Any]) -> str:
    for message in record["messages"]:
        if message.get("role") == "user":
            return str(message["content"])
    raise ValueError("missing user message")


COMPONENTS = ("schema", "action", "tool", "argument", "workflow", "stop")


def sha(value: Any) -> str:
    if isinstance(value, torch.Tensor):
        value = value.detach().cpu().numpy().tobytes()
    elif not isinstance(value, (bytes, bytearray)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(value).hexdigest()


def rng_state() -> dict[str, str]:
    out = {"torch_cpu": sha(torch.get_rng_state())}
    if torch.cuda.is_available():
        out["torch_cuda"] = sha(torch.cuda.get_rng_state())
    return out


def load_record(path: Path, sample_id: str) -> dict[str, Any]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if str(row.get("id")) == sample_id:
                return row
    raise KeyError(sample_id)


class TraceSchemaProcessor(LogitsProcessor):
    def __init__(self, tokenizer: Any, eos_token_id: int, prompt_length: int, parser_factory: Callable[[], Any], mandatory: list[str], trace: dict[str, Any], label: str, max_allowed_tokens: int = 256, scan_top_tokens: int = 8192):
        self.tokenizer = tokenizer
        self.eos_token_id = int(eos_token_id)
        self.prompt_length = int(prompt_length)
        self.parser_factory = parser_factory
        self.mandatory_ids = set()
        for fragment in mandatory:
            self.mandatory_ids.update(tokenizer.encode(fragment, add_special_tokens=False))
        self.max_allowed_tokens = max_allowed_tokens
        self.scan_top_tokens = scan_top_tokens
        self.trace = trace
        self.label = label
        self.row_state_cache: dict[int, tuple[str, Any]] = {}

    def _piece(self, token_id: int) -> str:
        return self.tokenizer.decode([int(token_id)], skip_special_tokens=False)

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        for row_index, row in enumerate(input_ids):
            completion_ids = row[self.prompt_length:].detach().cpu().tolist()
            completion = self.tokenizer.decode(completion_ids, skip_special_tokens=True)
            cached_text, cached_state = self.row_state_cache.get(row_index, ("", self.parser_factory()))
            state = cached_state.clone() if completion.startswith(cached_text) else self.parser_factory()
            suffix = completion[len(cached_text):] if completion.startswith(cached_text) else completion
            if not state.feed(suffix):
                raise RuntimeError(f"parser escaped schema at row={row_index}: {state.error}")
            self.row_state_cache[row_index] = (completion, state.clone())
            should_trace = len(completion_ids) <= 32
            ranked = torch.topk(scores[row_index], k=min(32, scores.size(-1))).indices.detach().cpu().tolist() if should_trace else []
            scan = min(512, self.scan_top_tokens, scores.size(-1))
            legal: list[int] = []
            while True:
                ranked_scan = torch.topk(scores[row_index], k=scan).indices.detach().cpu().tolist()
                for token_id in list(dict.fromkeys(ranked_scan + sorted(self.mandatory_ids))):
                    if token_id == self.eos_token_id or token_id >= scores.size(-1):
                        continue
                    piece = self._piece(token_id)
                    if not piece or piece.startswith("<|"):
                        continue
                    trial = state.clone()
                    if trial.feed(piece):
                        legal.append(int(token_id))
                        if len(legal) >= self.max_allowed_tokens:
                            break
                if legal or scan >= min(self.scan_top_tokens, scores.size(-1)):
                    break
                scan = min(scan * 2, self.scan_top_tokens, scores.size(-1))
            if should_trace:
                probs = torch.softmax(scores[row_index], dim=-1)
                self.trace.setdefault("steps", []).append({
                    "label": self.label,
                    "row": row_index,
                    "token_position": len(completion_ids),
                    "selected_prefix_sha256": sha(completion),
                    "parser_state": state.result().to_dict(),
                    "parser_error": state.error,
                    "top32_token_ids": ranked,
                    "top32_probs": [float(probs[i]) for i in ranked],
                    "legal_token_ids": legal[:32],
                    "legal_token_probs": [float(probs[i]) for i in legal[:32]],
                    "rng": rng_state(),
                })
            if state.result().complete:
                scores[row_index].fill_(float("-inf"))
                scores[row_index, self.eos_token_id] = 0.0
            else:
                original = scores[row_index, legal].clone()
                scores[row_index].fill_(float("-inf"))
                scores[row_index, legal] = original
        return scores


def build_prompt(record: dict[str, Any], processor: Any) -> tuple[list[dict[str, Any]], str]:
    prompt = [{"role": "system", "content": planner_system_prompt(record)}, {"role": "user", "content": user_content(record)}]
    prepare_multimodal_messages(prompt, num_images=1)
    text = maybe_apply_chat_template({"prompt": prompt}, processor)["prompt"]
    return text, sha(prompt)


def make_parser_factory(registry: Any) -> Callable[[], Any]:
    arg_props = union_argument_properties([tool.arguments_schema for tool in registry.tools])
    result_types = {value for tool in registry.tools for value in tool.output.result_types}
    coordinate_spaces = {tool.output.coordinate_space for tool in registry.tools}
    def factory():
        def complete(value):
            try:
                AgentRequest.from_dict(value, registry)
                return True
            except (AgentActionError, ValueError, TypeError):
                return False
        return AgentRequestPrefixParser(registry.names(), arg_props, result_types, coordinate_spaces, complete)
    return factory


def generate_case(model: Any, processor: Any, inputs: dict[str, Any], prompt_length: int, args: dict[str, Any], label: str, schema: bool, parser_factory: Callable[[], Any] | None, mandatory: list[str]) -> dict[str, Any]:
    trace: dict[str, Any] = {"label": label, "before_rng": rng_state(), "prompt_hash": sha(inputs["input_ids"][:, :prompt_length]), "generation_args": args}
    processors = []
    if schema:
        processors.append(TraceSchemaProcessor(processor.tokenizer, int(model.config.eos_token_id), prompt_length, parser_factory, mandatory, trace, label))
    generation = dict(args)
    generation["logits_processor"] = processors
    with torch.no_grad():
        result = model.generate(**inputs, **generation)
    completion_ids = result[:, prompt_length:]
    texts = processor.batch_decode(completion_ids, skip_special_tokens=True)
    trace["after_rng"] = rng_state()
    trace["candidate_token_ids"] = [row.detach().cpu().tolist() for row in completion_ids]
    trace["candidate_texts"] = texts
    trace["candidate_hashes"] = [sha(text) for text in texts]
    trace["eos"] = []
    for row in completion_ids:
        token_list = row.detach().cpu().tolist()
        eos_id = int(model.config.eos_token_id)
        trace["eos"].append({"has_eos": eos_id in token_list, "eos_index": token_list.index(eos_id) if eos_id in token_list else None})
    if schema and trace.get("steps"):
        trace["first_divergence_step"] = None
    return trace


def run(root: Path, output: Path, selected_case: str, seed: int = 20261011) -> None:
    output.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((root / "runs/hydro_remote_agent/vaguehydro_grpo_gold_action_reward_fix_v1/PREFLIGHT_ONLY_CONFIG.json").read_text(encoding="utf-8"))
    sample_id = cfg["data"]["train_sample_ids"][0]
    record = load_record(root / cfg["data"]["train"], sample_id)
    base = cfg["base_model"]
    processor = AutoProcessor.from_pretrained(base, max_pixels=65536, local_files_only=True)
    processor.tokenizer.padding_side = "left"
    model = Qwen3VLForConditionalGeneration.from_pretrained(base, dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True, low_cpu_mem_usage=True)
    model = PeftModel.from_pretrained(model, root / cfg["initial_sft_adapter"], is_trainable=False)
    model = model.to("cuda").eval()
    registry = load_tool_registry(root / "hydro_remote_agent/configs/tool_registry.yaml")
    parser_factory = make_parser_factory(registry)
    prompt_text, prompt_hash = build_prompt(record, processor)
    image = record["images"][0]
    inputs = processor(text=[prompt_text, prompt_text], images=[[image], [image]], return_tensors="pt", padding=True, max_length=8192, truncation=True, add_special_tokens=False)
    inputs = {key: value.to(model.device) if hasattr(value, "to") else value for key, value in inputs.items()}
    prompt_length = inputs["input_ids"].size(1)
    mandatory = ["{", "}", "[", "]", ":", ",", '"', "true", "false", "null", *AgentRequestPrefixParser.ROOT_KEYS, *AgentRequestPrefixParser.ACTION_KEYS, *AgentRequestPrefixParser.STEP_KEYS, *AgentRequestPrefixParser.EXPECTED_KEYS, *registry.names(), "1.0", "direct_answer", "tool_call", "workflow", "clarification", "abstain", "auto", "required", "skip"]
    eos_token_id = int(processor.tokenizer.eos_token_id)
    model.config.eos_token_id = eos_token_id
    common = {"do_sample": True, "temperature": 2.0, "top_p": 0.98, "max_new_tokens": 32, "eos_token_id": eos_token_id, "pad_token_id": int(processor.tokenizer.pad_token_id)}
    cases = {}
    if selected_case == "A":
        torch.manual_seed(seed); random.seed(seed); cases["A_native_no_schema"] = generate_case(model, processor, inputs, prompt_length, common, "A_native_no_schema", False, None, mandatory)
    elif selected_case == "B":
        torch.manual_seed(seed); random.seed(seed); cases["B_schema_current"] = generate_case(model, processor, inputs, prompt_length, common, "B_schema_current", True, parser_factory, mandatory)
    elif selected_case == "C":
        independent = []
        for row in range(2):
            torch.manual_seed(seed + row + 1)
            single = processor(text=[prompt_text], images=[[image]], return_tensors="pt", padding=True, max_length=8192, truncation=True, add_special_tokens=False)
            single = {key: value.to(model.device) if hasattr(value, "to") else value for key, value in single.items()}
            independent.append(generate_case(model, processor, single, single["input_ids"].size(1), common, f"C_schema_independent_row{row}", True, parser_factory, mandatory))
        cases["C_schema_independent"] = independent
    elif selected_case == "D":
        torch.manual_seed(seed); cases["D_repeat_1"] = generate_case(model, processor, inputs, prompt_length, common, "D_repeat_1", True, parser_factory, mandatory)
        torch.manual_seed(seed); cases["D_repeat_2"] = generate_case(model, processor, inputs, prompt_length, common, "D_repeat_2", True, parser_factory, mandatory)
    result = {"schema_version": "vaguehydro.sampling_diagnostic.v1", "sample_id": sample_id, "seed": seed, "prompt_hash": prompt_hash, "sampling": common, "frozen_test_read": False, "cases": cases}
    (output / f"TOKEN_TRACE_{selected_case}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=lambda value: value.tolist() if isinstance(value, torch.Tensor) else str(value)) + "\n", encoding="utf-8")
    comparison = {}
    for name, value in cases.items():
        hashes = value.get("candidate_hashes", []) if isinstance(value, dict) else [item for case in value for item in case.get("candidate_hashes", [])]
        comparison[name] = {"candidate_hashes": hashes, "unique_count": len(set(hashes))}
    (output / f"AB_COMPARISON_{selected_case}.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=("A", "B", "C", "D"), required=True)
    args = parser.parse_args()
    run(args.root.resolve(), args.output if args.output.is_absolute() else args.root / args.output, args.case)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
