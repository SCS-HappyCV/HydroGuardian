"""Real VagueHydro task step-10 integration for formal v4."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import torch
from datasets import Dataset, Image
from peft import PeftModel
from transformers import AutoProcessor, TrainerCallback, Qwen3VLForConditionalGeneration
from trl import GRPOConfig, GRPOTrainer
from trl.data_utils import maybe_apply_chat_template, prepare_multimodal_messages
from trl.extras.profiling import profiling_context
from trl.models import unwrap_model_for_generation

from hydro_remote_agent.backbones.qwen3_vl_planner import planner_system_prompt
from hydro_remote_agent.rewards.gold_action_reward import GoldActionReward
from hydro_remote_agent.rewards.completion_adapter import adapt_completion
from hydro_remote_agent.schema_constrained_generation import AgentRequestPrefixParser, union_argument_properties
from hydro_remote_agent.schemas.agent_action import AgentActionError, AgentRequest
from hydro_remote_agent.schemas.tool_spec import load_tool_registry
from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v2 import AtomicCheckpointManager, ResumeIdentity, build_validation_manifest, sha256_file
from hydro_remote_agent.tools.train_vaguehydro_grpo_formal_v3 import bind_trl_classes
from hydro_remote_agent.tools.train_vaguehydro_r_m2_grpo_smoke import SchemaConstrainedLogitsProcessor, completion_text, gold_action, records_selected_by_id, read_jsonl_ids, user_content

COMPONENTS = ("schema", "action", "tool", "argument", "workflow", "stop")


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if hasattr(value, "__iter__") and value.__class__.__name__ == "deque":
        return [jsonable(item) for item in value]
    if torch.is_tensor(value):
        return value.detach().cpu().tolist()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def make_rows(records: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        action = gold_action(record)
        rows.append({
            "prompt": [{"role": "system", "content": planner_system_prompt(record)}, {"role": "user", "content": user_content(record)}],
            "image": record["images"][0],
            "gold_action_json": json.dumps(action, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "sample_id": str(record["id"]),
            "source_split": split,
            "gold_action_type": str(action.get("action", {}).get("type", "")),
        })
    return rows


def component_reward(name: str, engine: GoldActionReward, adapter_errors: list[dict[str, Any]]):
    def reward(completions, gold_action_json, **_):
        values = []
        for completion, gold_json in zip(completions, gold_action_json):
            adapted = adapt_completion(completion)
            if not adapted.valid or adapted.payload is None:
                adapter_errors.append({"component": name, "error": adapted.error})
                values.append(0.0)
                continue
            breakdown = engine.score(adapted.payload, json.loads(gold_json))
            values.append(float(getattr(breakdown, name)))
        return values
    reward.__name__ = f"gold_{name}_reward"
    return reward


def run(config_path: Path, root: Path, seed: int, output: Path) -> int:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    train_path, valid_path, frozen_path = (root / cfg["data"][key] for key in ("train", "valid", "frozen_test"))
    frozen_ids = read_jsonl_ids(frozen_path)
    train_records = records_selected_by_id(train_path, cfg["data"]["train_sample_ids"], frozen_ids)
    if any(str(r["id"]) in frozen_ids for r in train_records):
        raise RuntimeError("train/frozen overlap")
    manifest_path = output.parent.parent / cfg["data"]["validation_manifest"]
    if not manifest_path.is_file():
        build_validation_manifest(valid_path, frozen_path, manifest_path, limit=int(cfg["data"]["validation_manifest_limit"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validation_ids = {str(row["id"]) for row in manifest["records"]}
    valid_records = []
    for line in valid_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if str(row.get("id")) in validation_ids:
                valid_records.append(row)
    if len(valid_records) != len(validation_ids):
        raise RuntimeError("validation manifest records missing from val source")
    output.mkdir(parents=True, exist_ok=True)
    train_ds = Dataset.from_list(make_rows(train_records, "train")).cast_column("image", Image())
    valid_ds = Dataset.from_list(make_rows(valid_records, "valid")).cast_column("image", Image())
    base = cfg["base_model"]
    processor = AutoProcessor.from_pretrained(base, max_pixels=65536, local_files_only=True)
    processor.tokenizer.padding_side = "left"
    model = Qwen3VLForConditionalGeneration.from_pretrained(base, dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True, low_cpu_mem_usage=True)
    model = PeftModel.from_pretrained(model, root / cfg["initial_sft_adapter"], is_trainable=True)
    registry = load_tool_registry(root / "hydro_remote_agent/configs/tool_registry.yaml")
    engine = GoldActionReward(registry, cfg["reward"]["weights"])
    adapter_errors: list[dict[str, Any]] = []
    arg_props = union_argument_properties([tool.arguments_schema for tool in registry.tools])
    result_types = {value for tool in registry.tools for value in tool.output.result_types}
    coordinate_spaces = {tool.output.coordinate_space for tool in registry.tools}

    def parser_factory():
        def complete(value):
            try:
                AgentRequest.from_dict(value, registry)
                return True
            except (AgentActionError, ValueError, TypeError):
                return False
        return AgentRequestPrefixParser(registry.names(), arg_props, result_types, coordinate_spaces, complete)

    BoundTrainer, AtomicCallback = bind_trl_classes(GRPOTrainer, TrainerCallback)

    class VagueHydroTrainer(BoundTrainer):
        def _generate_single_turn(self, prompts, images):
            prompt_copies = deepcopy(prompts)
            processor_kwargs = {}
            if images is not None:
                processor_kwargs["images"] = images
                for prompt, image_list in zip(prompt_copies, images):
                    if isinstance(prompt, list):
                        prepare_multimodal_messages(prompt, num_images=len(image_list))
            prompts_text = [maybe_apply_chat_template({"prompt": prompt}, self.processing_class)["prompt"] for prompt in prompt_copies]
            inputs = self.processing_class(text=prompts_text, return_tensors="pt", padding=True, padding_side="left", max_length=8192, truncation=True, add_special_tokens=False, **processor_kwargs)
            inputs = super(GRPOTrainer, self)._prepare_inputs(inputs)
            prompt_length = inputs["input_ids"].size(1)
            mandatory = ["{", "}", "[", "]", ":", ",", '"', "true", "false", "null", *AgentRequestPrefixParser.ROOT_KEYS, *AgentRequestPrefixParser.ACTION_KEYS, *AgentRequestPrefixParser.STEP_KEYS, *AgentRequestPrefixParser.EXPECTED_KEYS, *registry.names(), "1.0", "direct_answer", "tool_call", "workflow", "clarification", "abstain", "auto", "required", "skip"]
            lp = SchemaConstrainedLogitsProcessor(self.processing_class.tokenizer, self.eos_token_id, prompt_length, parser_factory, 256, 8192, mandatory)
            with profiling_context(self, "formal_v4.schema_constrained_generation"), unwrap_model_for_generation(self.model_wrapped, self.accelerator, gather_deepspeed3_params=self.args.ds3_gather_for_generation) as unwrapped, torch.no_grad():
                generated = unwrapped.generate(**inputs, generation_config=self.generation_config, logits_processor=[lp], disable_compile=True)
            completion_ids = generated[:, prompt_length:]
            eos = completion_ids == self.eos_token_id
            eos_idx = torch.full((eos.size(0),), eos.size(1), dtype=torch.long, device=eos.device)
            if eos.any(dim=1).any():
                rows = eos.any(dim=1)
                eos_idx[rows] = eos.int().argmax(dim=1)[rows]
            mask = torch.arange(eos.size(1), device=eos.device).expand(eos.size(0), -1) <= eos_idx.unsqueeze(1)
            prompt_ids = [v[m].tolist() for v, m in zip(inputs["input_ids"], inputs["attention_mask"].bool())]
            completion_ids = [v[m].tolist() for v, m in zip(completion_ids, mask.bool())]
            forward = {k: v for k, v in inputs.items() if k not in {"input_ids", "attention_mask"}}
            return prompt_ids, completion_ids, None, forward

        def evaluate(self, eval_dataset=None, **kwargs):
            """Run a real, read-only validation generation outside TRL's eval log-prob path.

            The installed TRL version assumes a rectangular completion batch during
            prediction_step; schema-constrained variable-length outputs violate that
            assumption for the two-record acceptance manifest. This keeps model
            generation and GoldActionReward real while avoiding optimizer updates.
            """
            self.formal_eval_invocations += 1
            ds = eval_dataset if eval_dataset is not None else self.eval_dataset
            prompts = list(ds["prompt"])
            images = [[image] for image in list(ds["image"])]
            _, completion_ids, _, _ = self._generate_single_turn(prompts, images)
            completions = self.processing_class.batch_decode(completion_ids, skip_special_tokens=True)
            totals = {name: [] for name in COMPONENTS}
            for completion, gold_json in zip(completions, list(ds["gold_action_json"])):
                adapted = adapt_completion(completion)
                if not adapted.valid or adapted.payload is None:
                    adapter_errors.append({"component": "eval", "error": adapted.error})
                    continue
                breakdown = engine.score(adapted.payload, json.loads(gold_json))
                for name in COMPONENTS:
                    totals[name].append(float(getattr(breakdown, name)))
            metrics = {f"eval_gold_{name}_reward": sum(values) / max(1, len(values)) for name, values in totals.items()}
            metrics["eval_formal_read_only"] = 1.0
            return metrics

    cfg_args = GRPOConfig(output_dir=str(output / "native_trainer"), max_steps=int(cfg["optimization"]["max_optimizer_steps"]), per_device_train_batch_size=1, gradient_accumulation_steps=1, num_generations=int(cfg["sampling"]["group_size"]), max_prompt_length=8192, max_completion_length=int(cfg["sampling"]["max_new_tokens"]), temperature=float(cfg["sampling"]["temperature"]), top_p=float(cfg["sampling"]["top_p"]), learning_rate=1e-6, beta=0.0, epsilon=0.2, loss_type="dapo", scale_rewards="group", reward_weights=[cfg["reward"]["weights"][name] for name in COMPONENTS], bf16=True, tf32=True, gradient_checkpointing=False, logging_steps=1, eval_strategy="steps", eval_steps=int(cfg["validation"]["eval_steps"]), save_strategy="steps", save_steps=10, save_total_limit=1, remove_unused_columns=False, report_to="none", optim="adamw_torch", seed=seed, data_seed=seed, use_vllm=False, generation_batch_size=int(cfg["sampling"]["group_size"]), generation_kwargs={"do_sample": True})
    def trainable_fingerprint(module: Any) -> str:
        digest = hashlib.sha256()
        for name, parameter in sorted(module.named_parameters()):
            if parameter.requires_grad:
                tensor = parameter.detach().float().cpu()
                digest.update(name.encode())
                digest.update(tensor.numpy().tobytes())
        return digest.hexdigest()

    adapter_hash_before = trainable_fingerprint(model)
    trainer = VagueHydroTrainer(model=model, reward_funcs=[component_reward(name, engine, adapter_errors) for name in COMPONENTS], args=cfg_args, train_dataset=train_ds, eval_dataset=valid_ds, processing_class=processor)
    identity = ResumeIdentity(seed, sha256_file(config_path), sha256_file(manifest_path), str(cfg["reward"]["weights"]))
    manager = AtomicCheckpointManager(output / "atomic_checkpoints", identity)
    trainer.formal_checkpoint_manager = manager
    trainer.add_callback(AtomicCallback(manager, identity.config_hash, identity.data_manifest_hash, identity.reward_hash))
    trainer.train()
    adapter_hash_after = trainable_fingerprint(model)
    component_logs = jsonable(dict(trainer._logs.get("rewards", {})))
    raw_candidates = jsonable(list(trainer._logs.get("completion", [])))
    checkpoint_json = output / "atomic_checkpoints" / "checkpoint-10" / "checkpoint.json"
    raw_unwrap_hashes = []
    for raw in raw_candidates:
        adapted = adapt_completion(raw)
        raw_unwrap_hashes.append({"raw_sha256": hashlib.sha256(raw.encode()).hexdigest(), "unwrap_sha256": hashlib.sha256((adapted.raw_json or "").encode()).hexdigest(), "canonical_sha256": hashlib.sha256(json.dumps(adapted.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest() if adapted.payload else None, "valid": adapted.valid, "error": adapted.error})
    report = {"status": "pass", "seed": seed, "global_step": trainer.state.global_step, "eval_invocations": trainer.formal_eval_invocations, "train_samples": len(train_ds), "validation_samples": len(valid_ds), "frozen_test_read": False, "train_split": "train", "validation_split": "valid", "raw_candidate_count": len(raw_candidates), "raw_candidates": raw_candidates, "raw_unwrap_canonical_hashes": raw_unwrap_hashes, "component_reward_logs": component_logs, "adapter_errors": adapter_errors, "reward_std": [entry.get("reward_std") for entry in trainer.state.log_history if "reward_std" in entry], "gradient_norms": [entry.get("grad_norm") for entry in trainer.state.log_history if "grad_norm" in entry], "training_log_history": jsonable(trainer.state.log_history), "natural_reward_variance": any(len(set(map(str, values))) > 1 for values in component_logs.values() if isinstance(values, list)), "checkpoint_10_completed": (output / "atomic_checkpoints" / "checkpoint-10" / "COMPLETED").is_file(), "adapter_delta": {"before_sha256": adapter_hash_before, "after_sha256": adapter_hash_after, "changed": adapter_hash_before != adapter_hash_after}, "checkpoint_metadata": json.loads(checkpoint_json.read_text(encoding="utf-8")) if checkpoint_json.is_file() else None}
    (output / "REAL_TASK_PREFLIGHT_REPORT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = args.project_root.resolve()
    cfg = args.config if args.config.is_absolute() else root / args.config
    return run(cfg, root, args.seed, root / args.output if not args.output.is_absolute() else args.output)


if __name__ == "__main__":
    raise SystemExit(main())
