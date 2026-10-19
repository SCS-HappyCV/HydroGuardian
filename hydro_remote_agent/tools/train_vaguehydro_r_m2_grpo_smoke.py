from __future__ import annotations

import argparse
from collections import deque
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
import math
import statistics
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import torch
from transformers import LogitsProcessor, LogitsProcessorList

from trl.extras.profiling import profiling_context
from trl.models import unwrap_model_for_generation

from hydro_remote_agent.backbones.qwen3_vl_planner import planner_system_prompt
from hydro_remote_agent.generation_termination import complete_json_prefix_end
from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.rewards.request_canonicalizer import canonicalize_agent_request
from hydro_remote_agent.schema_constrained_generation import (
    AgentRequestPrefixParser,
    is_non_progress_json_whitespace,
    union_argument_properties,
)
from hydro_remote_agent.schemas.agent_action import AgentActionError, AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry


COMPONENTS = ("schema", "action", "tool", "argument", "workflow", "stop")


class CompleteJsonEosLogitsProcessor(LogitsProcessor):
    """Force EOS on the token after a complete top-level JSON object."""

    def __init__(self, tokenizer: Any, eos_token_id: int, prompt_length: int) -> None:
        self.tokenizer = tokenizer
        self.eos_token_id = int(eos_token_id)
        self.prompt_length = int(prompt_length)

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        for row_index, row in enumerate(input_ids):
            completion_ids = row[self.prompt_length :].detach().cpu().tolist()
            if not completion_ids:
                continue
            text = self.tokenizer.decode(completion_ids, skip_special_tokens=True)
            if complete_json_prefix_end(text) is None:
                continue
            scores[row_index].fill_(float("-inf"))
            scores[row_index, self.eos_token_id] = 0.0
        return scores


class SchemaConstrainedLogitsProcessor(LogitsProcessor):
    """Mask every sampled token whose decoded text violates an AgentRequest prefix."""

    def __init__(
        self,
        tokenizer: Any,
        eos_token_id: int,
        prompt_length: int,
        parser_factory: Callable[[], AgentRequestPrefixParser],
        max_allowed_tokens: int,
        scan_top_tokens: int,
        mandatory_fragments: Sequence[str],
        exact_reparse: bool = False,
    ) -> None:
        self.tokenizer = tokenizer
        self.eos_token_id = int(eos_token_id)
        self.prompt_length = int(prompt_length)
        self.parser_factory = parser_factory
        self.max_allowed_tokens = int(max_allowed_tokens)
        self.scan_top_tokens = int(scan_top_tokens)
        self.exact_reparse = bool(exact_reparse)
        self._row_state_cache: dict[int, tuple[str, AgentRequestPrefixParser]] = {}
        mandatory_ids = set()
        for fragment in mandatory_fragments:
            for offset in range(len(fragment)):
                mandatory_ids.update(tokenizer.encode(fragment[offset:], add_special_tokens=False))
        self.mandatory_ids = mandatory_ids
        self.bridge_ids = {
            token_id
            for token_id in range(len(tokenizer))
            if "\ufffd" in tokenizer.decode([token_id], skip_special_tokens=False)
        } if self.exact_reparse else set()
        if self.exact_reparse:
            from transformers.models.gpt2.tokenization_gpt2 import bytes_to_unicode

            self.byte_decoder = {value: key for key, value in bytes_to_unicode().items()}
        else:
            self.byte_decoder = {}

    def _piece(self, token_id: int) -> str:
        return self.tokenizer.decode([token_id], skip_special_tokens=False)

    def _exact_prefix(self, token_ids: Sequence[int]) -> tuple[str, int] | None:
        raw = bytearray()
        for token_id in token_ids:
            token = self.tokenizer.convert_ids_to_tokens(int(token_id))
            if not isinstance(token, str) or token.startswith("<|"):
                return None
            try:
                raw.extend(self.byte_decoder[char] for char in token)
            except KeyError:
                raw.extend(token.encode("utf-8"))
        try:
            return bytes(raw).decode("utf-8"), 0
        except UnicodeDecodeError as error:
            if error.end == len(raw) and error.reason == "unexpected end of data":
                lead = raw[error.start]
                expected = 2 if lead < 0xE0 else (3 if lead < 0xF0 else 4)
                remaining = expected - (len(raw) - error.start)
                return bytes(raw[: error.start]).decode("utf-8"), remaining
            return None

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        vocab_size = scores.size(-1)
        for row_index, row in enumerate(input_ids):
            completion_ids = row[self.prompt_length :].detach().cpu().tolist()
            if self.exact_reparse:
                completion_prefix = self._exact_prefix(completion_ids)
                if completion_prefix is None:
                    raise RuntimeError("Generated token bytes are not a valid UTF-8 prefix")
                completion, pending_bytes = completion_prefix
            else:
                completion = self.tokenizer.decode(completion_ids, skip_special_tokens=True)
                pending_bytes = 0
            cached_text, cached_state = self._row_state_cache.get(row_index, ("", self.parser_factory()))
            if self.exact_reparse:
                state = self.parser_factory()
                suffix = completion
            elif completion.startswith(cached_text):
                state = cached_state.clone()
                suffix = completion[len(cached_text) :]
            else:
                state = self.parser_factory()
                suffix = completion
            if not state.feed(suffix):
                raise RuntimeError(f"Generated prefix escaped schema constraint: {state.error}")
            self._row_state_cache[row_index] = (completion, state.clone())
            if state.result().complete:
                scores[row_index].fill_(float("-inf"))
                scores[row_index, self.eos_token_id] = 0.0
                continue

            scan_count = min(512, self.scan_top_tokens, vocab_size)
            allowed: list[int] = []
            while True:
                ranked = torch.topk(scores[row_index], k=scan_count).indices.detach().cpu().tolist()
                candidate_ids = list(dict.fromkeys(
                    ranked + sorted(self.mandatory_ids) + sorted(self.bridge_ids)
                ))
                allowed = []
                for token_id in candidate_ids:
                    if token_id == self.eos_token_id or token_id >= vocab_size:
                        continue
                    if self.exact_reparse:
                        candidate_prefix = self._exact_prefix(completion_ids + [token_id])
                        if candidate_prefix is None:
                            continue
                        candidate_text, candidate_pending = candidate_prefix
                        if candidate_text == completion:
                            legal = pending_bytes > 0 and candidate_pending < pending_bytes
                        elif is_non_progress_json_whitespace(
                            state.result(), completion, candidate_text
                        ):
                            legal = False
                        else:
                            trial = self.parser_factory()
                            legal = trial.feed(candidate_text)
                    else:
                        piece = self._piece(token_id)
                        if not piece or piece.startswith("<|"):
                            continue
                        trial = state.clone()
                        legal = trial.feed(piece)
                    if legal:
                        allowed.append(token_id)
                        target_count = 1 if self.exact_reparse else self.max_allowed_tokens
                        if len(allowed) >= target_count:
                            break
                if allowed or scan_count >= min(self.scan_top_tokens, vocab_size):
                    break
                scan_count = min(scan_count * 2, self.scan_top_tokens, vocab_size)
            if not allowed:
                probes = []
                if self.exact_reparse:
                    for fragment in ('"', "\\", "a", " ", "}", "]", ",", ":"):
                        for token_id in self.tokenizer.encode(fragment, add_special_tokens=False):
                            probe_prefix = self._exact_prefix(completion_ids + [token_id])
                            probe_text = None if probe_prefix is None else probe_prefix[0]
                            probe_state = self.parser_factory()
                            probe_ok = probe_text is not None and probe_state.feed(probe_text)
                            probes.append((fragment, token_id, probe_ok, None if probe_text is None else probe_text[-80:], probe_state.error))
                raise RuntimeError(
                    f"Schema constraint found no legal token from {scan_count} ranked candidates "
                    f"at state={state.result().to_dict()} completion_tail={completion[-300:]!r} "
                    f"probes={probes!r}"
                )
            original = scores[row_index, allowed].clone()
            scores[row_index].fill_(float("-inf"))
            scores[row_index, allowed] = original
        return scores


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=json_default) + "\n",
        encoding="utf-8",
    )


def json_default(value: Any) -> Any:
    if isinstance(value, deque):
        return list(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def read_jsonl_ids(path: Path) -> set[str]:
    identifiers: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                identifiers.add(str(json.loads(line).get("id")))
    return identifiers


def selected_records(path: Path, count: int, excluded_ids: set[str]) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if str(record.get("id")) in excluded_ids:
                continue
            records.append(record)
            if len(records) == count:
                break
    if len(records) != count:
        raise ValueError(f"Requested {count} eligible records, found {len(records)}")
    return records


def structurally_selected_records(
    path: Path,
    quotas: Mapping[str, int],
    excluded_ids: set[str],
) -> list[dict[str, Any]]:
    remaining = {str(name): int(value) for name, value in quotas.items()}
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if str(record.get("id")) in excluded_ids:
                continue
            action_type = str(gold_action(record).get("action", {}).get("type", ""))
            if remaining.get(action_type, 0) <= 0:
                continue
            records.append(record)
            remaining[action_type] -= 1
            if all(value == 0 for value in remaining.values()):
                break
    missing = {name: value for name, value in remaining.items() if value > 0}
    if missing:
        raise ValueError(f"Could not satisfy structural action quotas: {missing}")
    return records


def records_selected_by_id(
    path: Path,
    sample_ids: Sequence[str],
    excluded_ids: set[str],
) -> list[dict[str, Any]]:
    requested = [str(value) for value in sample_ids]
    if len(requested) != len(set(requested)):
        raise ValueError("Explicit sample IDs must be unique")
    if any(identifier in excluded_ids for identifier in requested):
        raise ValueError("Explicit sample IDs overlap the frozen test")
    records_by_id: dict[str, dict[str, Any]] = {}
    requested_set = set(requested)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            identifier = str(record.get("id"))
            if identifier in requested_set:
                records_by_id[identifier] = record
                if len(records_by_id) == len(requested):
                    break
    missing = [identifier for identifier in requested if identifier not in records_by_id]
    if missing:
        raise ValueError(f"Explicit sample IDs are missing from train source: {missing}")
    return [records_by_id[identifier] for identifier in requested]


def gold_action(record: Mapping[str, Any]) -> dict[str, Any]:
    for message in reversed(record["messages"]):
        if message.get("role") == "assistant":
            value = json.loads(message["content"])
            if isinstance(value, dict):
                return value
    raise ValueError(f"Record {record.get('id')} has no assistant gold action")


def user_content(record: Mapping[str, Any]) -> str:
    for message in record["messages"]:
        if message.get("role") == "user":
            return str(message["content"])
    raise ValueError(f"Record {record.get('id')} has no user message")


def completion_text(completion: Any) -> str:
    if isinstance(completion, str):
        return completion
    if isinstance(completion, list) and completion:
        message = completion[-1]
        if isinstance(message, Mapping):
            content = message.get("content", "")
            if isinstance(content, str):
                return content
    return json.dumps(completion, ensure_ascii=False)


def structural_counterfactual(gold: Mapping[str, Any]) -> dict[str, Any]:
    candidate = deepcopy(gold)
    action = candidate.get("action", {})
    if action.get("type") != "tool_call":
        raise ValueError("Controlled v3 smoke requires a tool_call gold action")
    arguments = action.get("arguments", {})
    point_cloud_path = arguments.get("point_cloud_path")
    if not isinstance(point_cloud_path, str):
        raise ValueError("Controlled v3 smoke requires point_cloud_path")
    target_ids = list(arguments.get("target_class_ids", []))
    alternate_id = 8 if target_ids != [8] else 9
    action["tool"] = "point_semantic_segmentation"
    action["arguments"] = {
        "point_cloud_path": point_cloud_path,
        "target_class_ids": [alternate_id],
        "return_probabilities": True,
    }
    action["verification"] = "required"
    return candidate


def make_component_reward(
    component: str,
    reward_engine: GoldActionReward,
) -> Callable[..., list[float]]:
    def reward_function(
        completions: Sequence[Any],
        gold_action_json: Sequence[str],
        **_: Any,
    ) -> list[float]:
        values = []
        for completion, gold_json in zip(completions, gold_action_json):
            gold = json.loads(gold_json)
            allowed = [str(gold.get("action", {}).get("type", ""))]
            breakdown = reward_engine.score(
                completion_text(completion),
                gold,
                allowed_actions=allowed,
            )
            values.append(float(getattr(breakdown, component)))
        return values

    reward_function.__name__ = f"gold_{component}_reward"
    return reward_function


def preservation_status(root: Path, config: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    results = {}
    for relative_path in config["m1_preservation_files"]:
        current = sha256_file(root / relative_path)
        expected = baseline[relative_path]["sha256"]
        results[relative_path] = {
            "expected_sha256": expected,
            "current_sha256": current,
            "unchanged": current == expected,
        }
    return results


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the minimal VagueHydro-R Gold-Action GRPO smoke.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir = root / config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "SMOKE_REPORT.json"
    formal_grpo_started = False

    try:
        from datasets import Dataset, Image
        from peft import PeftModel
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
        from trl import GRPOConfig, GRPOTrainer
        from trl.data_utils import maybe_apply_chat_template, prepare_multimodal_messages

        environment = json.loads((output_dir / "environment_manifest.json").read_text(encoding="utf-8"))
        m1_manifest = json.loads((root / config["m1_manifest"]).read_text(encoding="utf-8"))
        train_path = root / config["train"]
        valid_path = root / config["valid"]
        frozen_path = root / config["frozen_test"]
        if sha256_file(train_path) != m1_manifest["sources"]["train"]["sha256"]:
            raise ValueError("Train source SHA256 does not match M1 manifest")
        if sha256_file(valid_path) != m1_manifest["sources"]["valid"]["sha256"]:
            raise ValueError("Validation source SHA256 does not match M1 manifest")
        if sha256_file(frozen_path) != m1_manifest["sources"]["frozen_test_exclusion_only"]["sha256"]:
            raise ValueError("Frozen-test SHA256 does not match M1 manifest")

        frozen_ids = read_jsonl_ids(frozen_path)
        selection_mode = str(config["data"].get("selection_mode", "first_eligible"))
        if selection_mode == "explicit_ids":
            records = records_selected_by_id(
                train_path,
                config["data"]["sample_ids"],
                frozen_ids,
            )
        elif selection_mode == "action_type_quota":
            records = structurally_selected_records(
                train_path,
                config["data"]["action_type_quotas"],
                frozen_ids,
            )
        else:
            records = selected_records(
                train_path,
                int(config["data"]["unique_prompt_samples"]),
                frozen_ids,
            )
        if len(records) != int(config["data"]["unique_prompt_samples"]):
            raise ValueError("Selected record count does not match unique_prompt_samples")
        rows = []
        for record in records:
            identifier = str(record["id"])
            images = record.get("images")
            if identifier in frozen_ids:
                raise ValueError(f"Selected frozen-test ID {identifier}")
            if not isinstance(images, list) or len(images) != 1:
                raise ValueError(f"Record {identifier} must contain exactly one image")
            rows.append(
                {
                    "prompt": [
                        {"role": "system", "content": planner_system_prompt(record)},
                        {"role": "user", "content": user_content(record)},
                    ],
                    "image": images[0],
                    "gold_action_json": json.dumps(
                        gold_action(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ),
                    "sample_id": identifier,
                    "source_split": "train",
                    "gold_action_type": str(gold_action(record).get("action", {}).get("type", "")),
                }
            )
        dataset = Dataset.from_list(rows).cast_column("image", Image())

        base_model_path = root / config["base_model"] if not Path(config["base_model"]).is_absolute() else Path(config["base_model"])
        adapter_path = root / config["sft_adapter"]
        processor = AutoProcessor.from_pretrained(
            base_model_path,
            max_pixels=int(config["data"]["max_image_pixels"]),
            local_files_only=True,
        )
        image_processor = getattr(processor, "image_processor", None)
        if image_processor is not None and hasattr(image_processor, "size"):
            image_size = dict(image_processor.size)
            image_size["longest_edge"] = int(config["data"]["max_image_pixels"])
            image_size["shortest_edge"] = min(
                int(image_size.get("shortest_edge", config["data"]["max_image_pixels"])),
                int(config["data"]["max_image_pixels"]),
            )
            image_processor.size = image_size
            if hasattr(image_processor, "max_pixels"):
                image_processor.max_pixels = int(config["data"]["max_image_pixels"])
        processor.tokenizer.padding_side = "left"
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            base_model_path,
            dtype=torch.bfloat16,
            attn_implementation="sdpa",
            local_files_only=True,
            low_cpu_mem_usage=True,
        )
        model.config.use_cache = False
        model = PeftModel.from_pretrained(model, adapter_path, is_trainable=True)
        trainable_parameters = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
        total_parameters = sum(parameter.numel() for parameter in model.parameters())

        registry = load_tool_registry(root / config["tool_registry"])
        reward_engine = GoldActionReward(registry, config["reward_weights"])
        argument_properties = union_argument_properties(
            [tool.arguments_schema for tool in registry.tools]
        )
        result_types = {value for tool in registry.tools for value in tool.output.result_types}
        coordinate_spaces = {tool.output.coordinate_space for tool in registry.tools}

        def complete_agent_request(value: Mapping[str, Any]) -> bool:
            try:
                AgentRequest.from_dict(value, registry)
            except (AgentActionError, ValueError, TypeError):
                return False
            return True

        def constrained_parser() -> AgentRequestPrefixParser:
            return AgentRequestPrefixParser(
                registry.names(),
                argument_properties,
                result_types,
                coordinate_spaces,
                complete_agent_request,
            )
        reward_functions = [make_component_reward(name, reward_engine) for name in COMPONENTS]
        grpo = config["grpo"]
        max_new_tokens = int(grpo.get("max_new_tokens", grpo["max_completion_length"]))
        if "max_completion_length" in grpo and int(grpo["max_completion_length"]) != max_new_tokens:
            raise ValueError("max_completion_length and max_new_tokens must match")
        if grpo.get("generation_mode") == "native_policy_sampling" and not bool(grpo.get("do_sample", True)):
            raise ValueError("Native policy sampling requires do_sample=true")
        controlled_completion_texts: Optional[list[str]] = None
        if grpo.get("generation_mode") == "controlled_gold_and_valid_structural_counterfactual":
            if len(records) != 1 or int(grpo["num_generations"]) != 2:
                raise ValueError("Controlled candidate smoke requires one prompt and two generations")
            gold_candidate = gold_action(records[0])
            counterfactual_candidate = structural_counterfactual(gold_candidate)
            candidate_evidence = []
            controlled_completion_texts = []
            for candidate_name, candidate in (
                ("gold", gold_candidate),
                ("valid_structural_counterfactual", counterfactual_candidate),
            ):
                text = json.dumps(
                    candidate,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                controlled_completion_texts.append(text)
                normalized = canonicalize_agent_request(candidate, registry)
                breakdown = reward_engine.score(
                    candidate,
                    gold_candidate,
                    allowed_actions=[str(gold_candidate["action"]["type"])],
                )
                candidate_evidence.append(
                    {
                        "candidate_name": candidate_name,
                        "completion": text,
                        "normalized_request": normalized.to_dict(),
                        "valid": normalized.valid,
                        "invalid": breakdown.invalid,
                        "reward": breakdown.to_dict(),
                    }
                )
            if not all(item["valid"] and not item["invalid"] for item in candidate_evidence):
                raise ValueError("Controlled candidates must both be valid AgentRequests")
            if math.isclose(
                candidate_evidence[0]["reward"]["total"],
                candidate_evidence[1]["reward"]["total"],
                abs_tol=1e-12,
            ):
                raise ValueError("Controlled candidates must receive different real Gold-Action rewards")
            write_json(
                output_dir / "candidate_reward_evidence.json",
                {
                    "schema_version": "vaguehydro_r.m2_controlled_candidates.v1",
                    "generation_mode": grpo["generation_mode"],
                    "policy_samples": False,
                    "reward_source": "GoldActionReward",
                    "gold_sample_id": rows[0]["sample_id"],
                    "candidates": candidate_evidence,
                },
            )

        class ControlledCandidateGRPOTrainer(GRPOTrainer):
            def __init__(self, *trainer_args: Any, controlled_texts: Sequence[str], **trainer_kwargs: Any) -> None:
                self.controlled_texts = list(controlled_texts)
                super().__init__(*trainer_args, **trainer_kwargs)

            def _generate_single_turn(self, prompts: list[Any], images: Optional[list[Any]]):
                prompt_copies = deepcopy(prompts)
                processor_kwargs: dict[str, Any] = {}
                if images is not None:
                    processor_kwargs["images"] = images
                    for prompt, image_list in zip(prompt_copies, images):
                        if isinstance(prompt, list):
                            prepare_multimodal_messages(prompt, num_images=len(image_list))
                prompts_text = [
                    maybe_apply_chat_template(
                        {"prompt": prompt},
                        self.processing_class,
                    )["prompt"]
                    for prompt in prompt_copies
                ]
                prompt_inputs = self.processing_class(
                    text=prompts_text,
                    return_tensors="pt",
                    padding=True,
                    padding_side="left",
                    max_length=self.max_prompt_length,
                    truncation=True,
                    add_special_tokens=False,
                    **processor_kwargs,
                ).to(self.accelerator.device)
                prompt_ids = [
                    values[mask.bool()].tolist()
                    for values, mask in zip(
                        prompt_inputs["input_ids"],
                        prompt_inputs["attention_mask"],
                    )
                ]
                if len(prompt_ids) != len(self.controlled_texts):
                    raise ValueError(
                        f"Expected {len(self.controlled_texts)} repeated prompts, got {len(prompt_ids)}"
                    )
                completion_ids = []
                for text in self.controlled_texts:
                    token_ids = self.processing_class.tokenizer.encode(
                        text,
                        add_special_tokens=False,
                    )
                    if not token_ids or token_ids[-1] != self.eos_token_id:
                        token_ids.append(self.eos_token_id)
                    completion_ids.append(token_ids)
                forward_kwargs = {
                    key: value
                    for key, value in prompt_inputs.items()
                    if key not in {"input_ids", "attention_mask"}
                }
                return prompt_ids, completion_ids, None, forward_kwargs

        class RecordingPolicyGRPOTrainer(GRPOTrainer):
            def __init__(self, *trainer_args: Any, **trainer_kwargs: Any) -> None:
                self.policy_sampling_trace: list[dict[str, Any]] = []
                self.generation_batch_index = 0
                super().__init__(*trainer_args, **trainer_kwargs)

            def _generate_single_turn(self, prompts: list[Any], images: Optional[list[Any]]):
                constrained = bool(grpo.get("schema_constrained_generation", False))
                if not constrained and not bool(grpo.get("stop_on_complete_json", False)):
                    return super()._generate_single_turn(prompts, images)
                if self.use_vllm or self.use_transformers_paged:
                    raise ValueError("Complete-JSON EOS termination requires regular Transformers generation")

                prompt_copies = deepcopy(prompts)
                processor_kwargs: dict[str, Any] = {}
                if images is not None:
                    processor_kwargs["images"] = images
                    for prompt, image_list in zip(prompt_copies, images):
                        if isinstance(prompt, list):
                            prepare_multimodal_messages(prompt, num_images=len(image_list))
                prompts_text = [
                    maybe_apply_chat_template({"prompt": prompt}, self.processing_class)["prompt"]
                    for prompt in prompt_copies
                ]
                generate_inputs = self.processing_class(
                    text=prompts_text,
                    return_tensors="pt",
                    padding=True,
                    padding_side="left",
                    max_length=self.max_prompt_length,
                    truncation=True,
                    add_special_tokens=False,
                    **processor_kwargs,
                )
                # Bypass GRPOTrainer._prepare_inputs, which would recursively start a
                # second generation pass when called from _generate_single_turn.
                generate_inputs = super(GRPOTrainer, self)._prepare_inputs(generate_inputs)
                prompt_length = generate_inputs["input_ids"].size(1)
                if constrained:
                    mandatory = [
                        "{", "}", "[", "]", ":", ",", '"', "true", "false", "null",
                        *AgentRequestPrefixParser.ROOT_KEYS,
                        *AgentRequestPrefixParser.ACTION_KEYS,
                        *AgentRequestPrefixParser.STEP_KEYS,
                        *AgentRequestPrefixParser.EXPECTED_KEYS,
                        *registry.names(),
                        "1.0", "direct_answer", "tool_call", "workflow", "clarification", "abstain",
                        "auto", "required", "skip",
                    ]
                    logits_processor = SchemaConstrainedLogitsProcessor(
                        self.processing_class.tokenizer,
                        self.eos_token_id,
                        prompt_length,
                        constrained_parser,
                        int(grpo.get("constraint_max_allowed_tokens", 256)),
                        int(grpo.get("constraint_scan_top_tokens", 8192)),
                        mandatory,
                    )
                else:
                    logits_processor = CompleteJsonEosLogitsProcessor(
                        self.processing_class.tokenizer,
                        self.eos_token_id,
                        prompt_length,
                    )
                logits_processors = LogitsProcessorList([logits_processor])
                with (
                    profiling_context(self, "transformers.generate.complete_json_eos"),
                    unwrap_model_for_generation(
                        self.model_wrapped,
                        self.accelerator,
                        gather_deepspeed3_params=self.args.ds3_gather_for_generation,
                    ) as unwrapped_model,
                    torch.no_grad(),
                    nullcontext(),
                ):
                    prompt_completion_ids = unwrapped_model.generate(
                        **generate_inputs,
                        generation_config=self.generation_config,
                        logits_processor=logits_processors,
                        disable_compile=True,
                    )
                prompt_ids = generate_inputs["input_ids"]
                prompt_mask = generate_inputs["attention_mask"]
                completion_ids = prompt_completion_ids[:, prompt_length:]
                is_eos = completion_ids == self.eos_token_id
                eos_idx = torch.full(
                    (is_eos.size(0),),
                    is_eos.size(1),
                    dtype=torch.long,
                    device=self.accelerator.device,
                )
                eos_idx[is_eos.any(dim=1)] = is_eos.int().argmax(dim=1)[is_eos.any(dim=1)]
                sequence_indices = torch.arange(is_eos.size(1), device=self.accelerator.device).expand(
                    is_eos.size(0), -1
                )
                completion_mask = (sequence_indices <= eos_idx.unsqueeze(1)).int()
                prompt_ids = [values[mask].tolist() for values, mask in zip(prompt_ids, prompt_mask.bool())]
                completion_ids = [values[mask].tolist() for values, mask in zip(completion_ids, completion_mask.bool())]
                forward_kwargs = {
                    key: value
                    for key, value in generate_inputs.items()
                    if key not in {"input_ids", "attention_mask"}
                }
                return prompt_ids, completion_ids, None, forward_kwargs

            def _generate_and_score_completions(self, inputs: list[dict[str, Any]]) -> dict[str, Any]:
                result = super()._generate_and_score_completions(inputs)
                completion_ids = result["completion_ids"]
                completion_mask = result["completion_mask"]
                advantages = result["advantages"].detach().cpu().tolist()
                decoded = self.processing_class.batch_decode(completion_ids, skip_special_tokens=True)
                for index, (row, completion, advantage) in enumerate(zip(inputs, decoded, advantages)):
                    active_ids = completion_ids[index][completion_mask[index].bool()].detach().cpu().tolist()
                    ended_with_eos = bool(active_ids and active_ids[-1] == self.eos_token_id)
                    ended_with_pad = bool(active_ids and active_ids[-1] == self.pad_token_id)
                    hit_length_limit = bool(len(active_ids) >= max_new_tokens and not ended_with_eos)
                    constraint_state = None
                    if bool(grpo.get("schema_constrained_generation", False)):
                        final_state = constrained_parser()
                        final_state.feed(completion)
                        constraint_state = final_state.result().to_dict()
                    self.policy_sampling_trace.append(
                        {
                            "generation_batch_index": self.generation_batch_index,
                            "candidate_index_in_batch": index,
                            "sample_id": str(row["sample_id"]),
                            "source_split": str(row["source_split"]),
                            "gold_action_json": str(row["gold_action_json"]),
                            "raw_completion": completion,
                            "raw_completion_token_ids": active_ids,
                            "advantage": float(advantage),
                            "completion_token_count": len(active_ids),
                            "ended_with_eos": ended_with_eos,
                            "ended_with_pad": ended_with_pad,
                            "hit_length_limit": hit_length_limit,
                            "complete_json_detected": complete_json_prefix_end(completion) is not None,
                            "constraint_state": constraint_state,
                            "clipped": hit_length_limit,
                        }
                    )
                self.generation_batch_index += 1
                return result

        training_args = GRPOConfig(
            output_dir=str(output_dir / "trainer"),
            max_steps=int(grpo["max_steps"]),
            per_device_train_batch_size=int(grpo["per_device_train_batch_size"]),
            gradient_accumulation_steps=int(grpo["gradient_accumulation_steps"]),
            num_generations=int(grpo["num_generations"]),
            max_prompt_length=int(grpo["max_prompt_length"]),
            max_completion_length=max_new_tokens,
            temperature=float(grpo["temperature"]),
            top_p=float(grpo["top_p"]),
            learning_rate=float(grpo["learning_rate"]),
            beta=float(grpo["beta"]),
            epsilon=float(grpo["epsilon"]),
            loss_type=str(grpo["loss_type"]),
            scale_rewards=str(grpo["scale_rewards"]),
            reward_weights=[float(config["reward_weights"][name]) for name in COMPONENTS],
            bf16=True,
            tf32=True,
            gradient_checkpointing=bool(grpo.get("gradient_checkpointing", True)),
            gradient_checkpointing_kwargs={"use_reentrant": False},
            logging_strategy="steps",
            logging_steps=1,
            save_strategy="steps",
            save_steps=1,
            save_total_limit=int(grpo.get("save_total_limit", 1)),
            remove_unused_columns=False,
            report_to="none",
            optim=str(grpo.get("optimizer", "adamw_torch_fused")),
            seed=int(config["seed"]),
            data_seed=int(config["seed"]),
            use_vllm=False,
            generation_batch_size=int(
                grpo.get(
                    "generation_batch_size",
                    int(grpo["per_device_train_batch_size"]) * int(grpo["gradient_accumulation_steps"]),
                )
            ),
            generation_kwargs={"do_sample": bool(grpo.get("do_sample", True))},
        )
        if controlled_completion_texts is not None:
            trainer_class = ControlledCandidateGRPOTrainer
        elif bool(grpo.get("record_all_policy_samples", False)):
            trainer_class = RecordingPolicyGRPOTrainer
        else:
            trainer_class = GRPOTrainer
        trainer_kwargs: dict[str, Any] = {}
        if controlled_completion_texts is not None:
            trainer_kwargs["controlled_texts"] = controlled_completion_texts
        trainer = trainer_class(
            model=model,
            reward_funcs=reward_functions,
            args=training_args,
            train_dataset=dataset,
            processing_class=processor,
            **trainer_kwargs,
        )
        torch.cuda.reset_peak_memory_stats()
        formal_grpo_started = True
        result = trainer.train()
        peak_gpu_memory_gib = torch.cuda.max_memory_allocated() / (1024 ** 3)
        final_checkpoint = output_dir / "checkpoint-final"
        trainer.save_model(final_checkpoint)
        processor.save_pretrained(final_checkpoint)
        trainer.state.save_to_json(str(output_dir / "trainer_state.json"))

        policy_sampling_trace = list(getattr(trainer, "policy_sampling_trace", []))
        logs = {
            "trainer_log_history": trainer.state.log_history,
            "prompts": trainer._logs["prompt"],
            "completions": trainer._logs["completion"],
            "component_rewards": dict(trainer._logs["rewards"]),
            "advantages": trainer._logs["advantages"],
            "all_policy_sampling_trace": policy_sampling_trace,
        }
        if policy_sampling_trace:
            full_component_rewards = {f"gold_{name}_reward": [] for name in COMPONENTS}
            for item in policy_sampling_trace:
                gold = json.loads(item["gold_action_json"])
                breakdown = reward_engine.score(
                    item["raw_completion"],
                    gold,
                    allowed_actions=[str(gold.get("action", {}).get("type", ""))],
                )
                for name in COMPONENTS:
                    full_component_rewards[f"gold_{name}_reward"].append(float(getattr(breakdown, name)))
            logs["completions"] = [item["raw_completion"] for item in policy_sampling_trace]
            logs["component_rewards"] = full_component_rewards
            logs["advantages"] = [item["advantage"] for item in policy_sampling_trace]
            write_json(output_dir / "policy_sampling_trace.json", policy_sampling_trace)
        write_json(output_dir / "reward_log_history.json", logs)
        advantages = [float(value) for value in logs["advantages"]]
        component_rewards = {
            name: [float(value) for value in values]
            for name, values in logs["component_rewards"].items()
        }
        total_rewards = [
            sum(
                float(config["reward_weights"][component])
                * component_rewards[f"gold_{component}_reward"][index]
                for component in COMPONENTS
            )
            for index in range(len(advantages))
        ]
        final_step_checkpoint = output_dir / "trainer" / f"checkpoint-{trainer.state.global_step}"
        optimizer_checkpoint = final_step_checkpoint / "optimizer.pt"
        checkpoint_adapter = final_step_checkpoint / "adapter_model.safetensors"
        initial_adapter = adapter_path / "adapter_model.safetensors"
        adapter_changed = (
            checkpoint_adapter.is_file()
            and sha256_file(checkpoint_adapter) != sha256_file(initial_adapter)
        )
        grad_norm_values = [
            float(entry["grad_norm"])
            for entry in trainer.state.log_history
            if "grad_norm" in entry and math.isfinite(float(entry["grad_norm"]))
        ]
        positive_gradient_norms = [value for value in grad_norm_values if value > 0.0]
        gradient_norm = positive_gradient_norms[-1] if positive_gradient_norms else (
            grad_norm_values[-1] if grad_norm_values else None
        )
        backward_evidence = bool(positive_gradient_norms)
        reward_std = statistics.stdev(total_rewards) if len(total_rewards) > 1 else 0.0
        nonzero_advantages = sum(not math.isclose(value, 0.0, abs_tol=1e-8) for value in advantages)
        expected_candidate_count = len(rows) * int(grpo["num_generations"])
        if policy_sampling_trace:
            expected_candidate_count *= int(grpo["max_steps"])
        checks = {
            "adapter_loaded_trainable": trainable_parameters > 0,
            "sampling_recorded": len(logs["completions"]) == expected_candidate_count,
            "reward_recorded": len(total_rewards) == expected_candidate_count,
            "advantage_recorded": len(advantages) == expected_candidate_count,
            "backward_recorded": backward_evidence,
            "optimizer_step_recorded": trainer.state.global_step == int(grpo["max_steps"]),
            "checkpoint_recorded": final_step_checkpoint.is_dir() and optimizer_checkpoint.is_file(),
            "final_adapter_recorded": (final_checkpoint / "adapter_model.safetensors").is_file(),
            "positive_reward_std": reward_std > 0.0,
            "nonzero_advantage": nonzero_advantages > 0,
            "nonzero_gradient_norm": backward_evidence,
            "adapter_changed": adapter_changed,
            "frozen_test_not_used": all(row["sample_id"] not in frozen_ids for row in rows),
            "m1_unchanged": all(
                item["unchanged"]
                for item in preservation_status(
                    root,
                    config,
                    environment["m1_preservation_baseline"],
                ).values()
            ),
            "no_expert_or_verifier": not config["constraints"]["call_real_experts"]
            and not config["constraints"]["call_verifier"],
        }
        smoke_pass = all(checks.values())
        gaps = []
        if nonzero_advantages == 0:
            gaps.append("The sampled group produced zero-variance reward and zero advantages; broaden M3 sampling.")
        if not any(value > 0.0 for value in total_rewards):
            gaps.append("No sampled completion received positive Gold-Action Reward.")
        if not adapter_changed:
            gaps.append("The checkpoint adapter is byte-identical to the initial SFT adapter.")
        if not backward_evidence:
            gaps.append("No positive finite gradient norm was recorded.")
        ready_for_m3 = smoke_pass
        report = {
            "schema_version": "vaguehydro_r.m2_smoke_report.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pass" if smoke_pass else "blocked",
            "formal_grpo_started": formal_grpo_started,
            "smoke_pass": smoke_pass,
            "ready_for_m3": ready_for_m3,
            "gpu": {
                "visible_device": 0,
                "name": torch.cuda.get_device_name(0),
                "peak_memory_gib": peak_gpu_memory_gib,
            },
            "data": {
                "split": "train",
                "unique_samples": len(rows),
                "sample_ids": [row["sample_id"] for row in rows],
                "gold_action_types": [row["gold_action_type"] for row in rows],
                "selection_mode": selection_mode,
                "num_generations": int(grpo["num_generations"]),
                "expected_candidate_count": expected_candidate_count,
                "max_image_pixels": int(config["data"]["max_image_pixels"]),
                "processor_image_size": dict(getattr(image_processor, "size", {})),
                "frozen_test_samples": 0,
            },
            "model": {
                "base_model": str(base_model_path),
                "sft_adapter": str(adapter_path),
                "trainable_parameters": trainable_parameters,
                "total_parameters": total_parameters,
            },
            "training": {
                "global_step": trainer.state.global_step,
                "train_loss": result.training_loss,
                "gradient_checkpointing": bool(grpo.get("gradient_checkpointing", True)),
                "optimizer": str(grpo.get("optimizer", "adamw_torch_fused")),
                "generation_mode": str(grpo.get("generation_mode", "model_sampling")),
                "do_sample": bool(grpo.get("do_sample", True)),
                "temperature": float(grpo["temperature"]),
                "top_p": float(grpo["top_p"]),
                "max_new_tokens": max_new_tokens,
                "total_rewards": total_rewards,
                "reward_std": reward_std,
                "advantages": advantages,
                "nonzero_advantage_count": nonzero_advantages,
                "gradient_norm": gradient_norm,
                "gradient_norm_history": grad_norm_values,
                "initial_adapter_sha256": sha256_file(initial_adapter),
                "checkpoint_adapter_sha256": sha256_file(checkpoint_adapter),
                "adapter_changed": adapter_changed,
            },
            "called_real_experts": False,
            "called_verifier": False,
            "checks": checks,
            "m1_preservation": preservation_status(
                root,
                config,
                environment["m1_preservation_baseline"],
            ),
            "artifacts": {
                "trainer_checkpoint": str(final_step_checkpoint.relative_to(root)),
                "final_adapter": str(final_checkpoint.relative_to(root)),
                "reward_log_history": str((output_dir / "reward_log_history.json").relative_to(root)),
                "policy_sampling_trace": (
                    str((output_dir / "policy_sampling_trace.json").relative_to(root))
                    if policy_sampling_trace
                    else None
                ),
                "candidate_reward_evidence": (
                    str((output_dir / "candidate_reward_evidence.json").relative_to(root))
                    if controlled_completion_texts is not None
                    else None
                ),
            },
            "implementation_hashes": {
                "training_entry": sha256_file(Path(__file__)),
                "config": sha256_file(config_path),
                "gold_action_reward": sha256_file(root / "hydro_remote_agent/rewards/gold_action_reward.py"),
                "canonicalizer": sha256_file(root / "hydro_remote_agent/rewards/request_canonicalizer.py"),
            },
            "gaps": gaps,
        }
        write_json(report_path, report)
        write_json(output_dir / "M2_REPORT.json", report)
        (output_dir / "M2_REPORT.md").write_text(
            "\n".join(
                [
                    "# VagueHydro-R M2 v3 Smoke Report",
                    "",
                    f"- Status: **{report['status'].upper()}**",
                    f"- Formal GRPO started: `{formal_grpo_started}`",
                    f"- Smoke pass: `{smoke_pass}`",
                    f"- Ready for M3: `{ready_for_m3}`",
                    f"- Global step: `{trainer.state.global_step}`",
                    f"- Reward std: `{reward_std}`",
                    f"- Nonzero advantages: `{nonzero_advantages}`",
                    f"- Gradient norm: `{gradient_norm}`",
                    f"- Adapter changed: `{adapter_changed}`",
                    "- Frozen-test samples: `0`",
                    "- Real experts called: `False`",
                    "- Verifier called: `False`",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (output_dir / "GAP_LIST.md").write_text(
            "# VagueHydro-R M2 Gap List\n\n"
            + ("\n".join(f"- {gap}" for gap in gaps) if gaps else "- None for the one-step smoke gate.")
            + "\n",
            encoding="utf-8",
        )
        print(
            f"VAGUEHYDRO_R_M2 status={report['status']} global_step={trainer.state.global_step} "
            f"ready_for_m3={ready_for_m3} output={output_dir}"
        )
        return 0 if smoke_pass else 2
    except Exception as error:
        failure = {
            "schema_version": "vaguehydro_r.m2_smoke_report.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "formal_grpo_started": formal_grpo_started,
            "smoke_pass": False,
            "ready_for_m3": False,
            "called_real_experts": False,
            "called_verifier": False,
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
            "gaps": ["Resolve the recorded GRPO smoke blocker before M3."],
        }
        write_json(report_path, failure)
        write_json(output_dir / "M2_REPORT.json", failure)
        (output_dir / "M2_REPORT.md").write_text(
            "\n".join(
                [
                    "# VagueHydro-R M2 Smoke Report",
                    "",
                    "- Status: **BLOCKED**",
                    f"- Formal GRPO started: `{formal_grpo_started}`",
                    "- Smoke pass: `False`",
                    "- Ready for M3: `False`",
                    f"- Error: `{type(error).__name__}: {error}`",
                    "- Real experts called: `False`",
                    "- Verifier called: `False`",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (output_dir / "GAP_LIST.md").write_text(
            "# VagueHydro-R M2 Gap List\n\n"
            f"- BLOCKED: {type(error).__name__}: {error}\n",
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
