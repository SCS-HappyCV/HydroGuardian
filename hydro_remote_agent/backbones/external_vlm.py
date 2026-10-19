from __future__ import annotations

import json
import time
from math import sqrt
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple


SUPPORTED_FAMILIES = ("glm4v", "deepseek_vl2")
EXTERNAL_AGENT_TOOL_NAMES = (
    "geometry_relation_analysis",
    "image_change_detection",
    "language_guided_point_segmentation",
    "multimodal_semantic_segmentation",
    "point_semantic_segmentation",
    "result_quality_verification",
)


class AllowedTokensLogitsProcessor:
    """Apply a token-enforcer callback without assuming non-empty input IDs."""

    def __init__(self, allowed_tokens_fn: Any, tokenizer: Any) -> None:
        self.allowed_tokens_fn = allowed_tokens_fn
        self.tokenizer = tokenizer

    def __call__(self, input_ids: Any, scores: Any) -> Any:
        constrained = scores.new_full(scores.shape, float("-inf"))
        for batch_id in range(scores.shape[0]):
            allowed = self.allowed_tokens_fn(batch_id, input_ids[batch_id])
            eos_token_id = self.tokenizer.eos_token_id
            if eos_token_id in allowed:
                decoded = self.tokenizer.decode(
                    input_ids[batch_id].detach().cpu().tolist(),
                    skip_special_tokens=True,
                )
                try:
                    complete = isinstance(json.loads(decoded), dict)
                except (json.JSONDecodeError, TypeError):
                    complete = False
                if not complete:
                    allowed = [token_id for token_id in allowed if token_id != eos_token_id]
            constrained[batch_id, allowed] = scores[batch_id, allowed]
        return constrained


def _message_text(message: Mapping[str, Any]) -> str:
    return "\n".join(
        str(block.get("text", ""))
        for block in message.get("content", [])
        if isinstance(block, Mapping) and block.get("type") == "text"
    ).strip()


def adapt_messages_for_family(
    messages: List[Dict[str, Any]],
    family: str,
    assistant_prefix: str = "",
) -> List[Dict[str, Any]]:
    """Translate the shared planner message format to a model-family format."""
    if family not in SUPPORTED_FAMILIES:
        raise ValueError(f"Unsupported external VLM family {family!r}")
    if family == "deepseek_vl2":
        user_messages = [message for message in messages if message.get("role") == "user"]
        if len(user_messages) != 1:
            raise ValueError("DeepSeek-VL2 expects exactly one user message")
        user_message = user_messages[0]
        image_paths = [
            str(block.get("image", ""))
            for block in user_message.get("content", [])
            if isinstance(block, Mapping) and block.get("type") == "image"
        ]
        if not image_paths or any(not path for path in image_paths):
            raise ValueError("DeepSeek-VL2 user message is missing an image path")
        placeholders = "\n".join("<image>" for _ in image_paths)
        return [
            {
                "role": "<|User|>",
                "content": f"{placeholders}\n{_message_text(user_message)}",
                "images": image_paths,
            },
            {"role": "<|Assistant|>", "content": assistant_prefix},
        ]

    adapted: List[Dict[str, Any]] = []
    for message in messages:
        content = []
        for block in message.get("content", []):
            item = dict(block)
            if item.get("type") == "image":
                image_path = item.pop("image", None)
                if not image_path:
                    raise ValueError("Image message is missing its local path")
                item["url"] = str(image_path)
            content.append(item)
        adapted.append({"role": str(message["role"]), "content": content})
    return adapted


def extract_system_prompt(messages: List[Dict[str, Any]]) -> str:
    return "\n".join(
        _message_text(message)
        for message in messages
        if message.get("role") == "system"
    ).strip()


def render_assistant_prefix(
    messages: List[Dict[str, Any]], prefix: str, prefix_template: str
) -> str:
    if not prefix_template:
        return prefix
    user_message = next(
        (message for message in messages if message.get("role") == "user"), None
    )
    if user_message is None:
        raise ValueError("Assistant prefix template requires a user message")
    payload = json.loads(_message_text(user_message))
    request_id = str(payload.get("request_id", ""))
    if not request_id:
        raise ValueError("Assistant prefix template requires request_id")
    escaped_request_id = json.dumps(request_id, ensure_ascii=False)[1:-1]
    return prefix_template.replace("{request_id}", escaped_request_id)


def request_id_from_messages(messages: List[Dict[str, Any]]) -> str:
    user_message = next(
        (message for message in messages if message.get("role") == "user"), None
    )
    if user_message is None:
        raise ValueError("AgentRequest constraint requires a user message")
    payload = json.loads(_message_text(user_message))
    request_id = str(payload.get("request_id", ""))
    if not request_id:
        raise ValueError("AgentRequest constraint requires request_id")
    return request_id


def agent_request_json_schema(request_id: str) -> Dict[str, Any]:
    non_empty_string = {"type": "string", "minLength": 1}
    verification = {"type": "string", "enum": ["auto", "required", "skip"]}
    tool_name = {"type": "string", "enum": list(EXTERNAL_AGENT_TOOL_NAMES)}
    workflow_step = {
        "type": "object",
        "properties": {
            "step_id": {
                "type": "string",
                "pattern": "^[A-Za-z][A-Za-z0-9_-]*$",
            },
            "tool": tool_name,
            "arguments": {"type": "object"},
            "depends_on": {"type": "array", "items": non_empty_string},
            "verification": verification,
        },
        "required": ["step_id", "tool", "arguments", "depends_on", "verification"],
        "additionalProperties": False,
    }
    action = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": [
                    "direct_answer",
                    "tool_call",
                    "workflow",
                    "clarification",
                    "abstain",
                ],
            },
            "answer": non_empty_string,
            "tool": tool_name,
            "arguments": {"type": "object"},
            "verification": verification,
            "steps": {
                "type": "array",
                "items": workflow_step,
                "minItems": 1,
                "maxItems": 4,
            },
            "question": non_empty_string,
            "missing_fields": {"type": "array", "items": non_empty_string},
            "reason": non_empty_string,
            "error_code": non_empty_string,
            "recoverable": {"type": "boolean"},
        },
        "required": ["type"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "schema_version": {"type": "string", "enum": ["1.0"]},
            "request_id": {"type": "string", "enum": [request_id]},
            "intent": {"type": "string", "minLength": 1, "maxLength": 64},
            "action": action,
            "expected_output": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "change_mask",
                            "geometry_report",
                            "image_mask",
                            "point_labels",
                            "point_mask",
                            "quality_report",
                            "text",
                        ],
                    },
                    "coordinate_space": non_empty_string,
                },
                "required": ["type", "coordinate_space"],
                "additionalProperties": False,
            },
        },
        "required": [
            "schema_version",
            "request_id",
            "intent",
            "action",
            "expected_output",
        ],
        "additionalProperties": False,
    }


def resize_image_to_pixel_budget(image: Any, max_image_pixels: int) -> Any:
    """Return a copy constrained by area while preserving aspect ratio."""
    if max_image_pixels <= 0:
        raise ValueError("max_image_pixels must be positive")
    width, height = image.size
    area = int(width) * int(height)
    if area <= max_image_pixels:
        return image.copy()
    scale = sqrt(max_image_pixels / float(area))
    target = (max(1, int(width * scale)), max(1, int(height * scale)))
    from PIL import Image

    resampling = getattr(Image, "Resampling", Image).LANCZOS
    return image.resize(target, resampling)


def cap_image_processor_pixels(processor: Any, max_image_pixels: int) -> None:
    if max_image_pixels <= 0:
        raise ValueError("max_image_pixels must be positive")
    image_processor = getattr(processor, "image_processor", None)
    size = getattr(image_processor, "size", None)
    if isinstance(size, Mapping):
        shortest_edge = size.get("shortest_edge")
        longest_edge = size.get("longest_edge")
    else:
        shortest_edge = getattr(size, "shortest_edge", None)
        longest_edge = getattr(size, "longest_edge", None)
    if longest_edge is None:
        raise ValueError("External VLM image processor does not expose longest_edge")
    if isinstance(size, Mapping):
        capped_size: Any = dict(size)
        capped_size["longest_edge"] = int(max_image_pixels)
    else:
        kwargs = {"longest_edge": int(max_image_pixels)}
        if shortest_edge is not None:
            kwargs["shortest_edge"] = int(shortest_edge)
        try:
            capped_size = type(size)(**kwargs)
        except TypeError:
            setattr(size, "longest_edge", int(max_image_pixels))
            capped_size = size
    image_processor.size = capped_size
    observed = (
        image_processor.size.get("longest_edge")
        if isinstance(image_processor.size, Mapping)
        else getattr(image_processor.size, "longest_edge", None)
    )
    if observed != int(max_image_pixels):
        raise ValueError("Failed to apply the shared external VLM image pixel cap")


class ExternalVLMGenerator:
    """Lazy Transformers generator for independently developed VLM families."""

    def __init__(
        self,
        config: Mapping[str, Any],
        model_path: str,
        max_new_tokens: int,
        max_image_pixels: int,
    ) -> None:
        import torch

        self.family = str(config["family"])
        if self.family not in SUPPORTED_FAMILIES:
            raise ValueError(f"Unsupported external VLM family {self.family!r}")
        self.torch = torch
        self.max_new_tokens = max(int(max_new_tokens), 1)
        self.max_image_pixels = int(max_image_pixels)
        self.enable_thinking = bool(config.get("enable_thinking", False))
        self.assistant_prefix = str(config.get("assistant_prefix", ""))
        self.assistant_prefix_template = str(config.get("assistant_prefix_template", ""))
        self.constraint_prompt = str(config.get("constraint_prompt", "")).strip()
        self.json_schema_constraint = bool(config.get("json_schema_constraint", False))
        self.lmfe_tokenizer_data: Any = None
        self.processor: Any
        self.model: Any
        self.tokenizer: Any = None
        started = time.perf_counter()
        if self.family == "glm4v":
            self._load_glm4v(config, model_path)
        else:
            self._load_deepseek_vl2(config, model_path)
        print(
            f"EXTERNAL_VLM_READY family={self.family} "
            f"seconds={time.perf_counter() - started:.2f}",
            flush=True,
        )

    def _dtype(self, config: Mapping[str, Any]) -> Any:
        return self.torch.bfloat16 if config.get("dtype") == "bfloat16" else self.torch.float16

    def _load_glm4v(self, config: Mapping[str, Any], model_path: str) -> None:
        from transformers import AutoProcessor, Glm4vForConditionalGeneration

        self.processor = AutoProcessor.from_pretrained(
            model_path,
            local_files_only=True,
            trust_remote_code=bool(config.get("trust_remote_code", False)),
        )
        cap_image_processor_pixels(self.processor, self.max_image_pixels)
        self.model = Glm4vForConditionalGeneration.from_pretrained(
            model_path,
            torch_dtype=self._dtype(config),
            device_map={"": 0},
            local_files_only=True,
            trust_remote_code=bool(config.get("trust_remote_code", False)),
        ).eval()

    def _load_deepseek_vl2(self, config: Mapping[str, Any], model_path: str) -> None:
        from deepseek_vl2.models import DeepseekVLV2Processor
        from transformers import AutoModelForCausalLM

        self.processor = DeepseekVLV2Processor.from_pretrained(
            model_path,
            local_files_only=True,
            trust_remote_code=True,
        )
        self.tokenizer = self.processor.tokenizer
        if self.json_schema_constraint:
            from lmformatenforcer.integrations.transformers import (
                build_token_enforcer_tokenizer_data,
            )

            self.lmfe_tokenizer_data = build_token_enforcer_tokenizer_data(self.tokenizer)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=self._dtype(config),
            device_map={"": 0},
            low_cpu_mem_usage=True,
            local_files_only=True,
            trust_remote_code=True,
        ).eval()

    def generate(self, messages: List[Dict[str, Any]]) -> Tuple[str, int, float]:
        if self.family == "deepseek_vl2":
            return self._generate_deepseek_vl2(messages)
        return self._generate_glm4v(messages)

    def _generate_glm4v(self, messages: List[Dict[str, Any]]) -> Tuple[str, int, float]:
        model_messages = adapt_messages_for_family(messages, self.family)
        inputs = self.processor.apply_chat_template(
            model_messages,
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=self.enable_thinking,
            return_dict=True,
            return_tensors="pt",
        ).to("cuda")
        inputs.pop("token_type_ids", None)
        started = time.perf_counter()
        with self.torch.inference_mode():
            generated = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
            )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        prompt_length = int(inputs["input_ids"].shape[1])
        trimmed = generated[:, prompt_length:]
        token_count = int(trimmed.shape[1])
        text = self.processor.batch_decode(
            trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()
        return text, token_count, elapsed_ms

    def _generate_deepseek_vl2(
        self, messages: List[Dict[str, Any]]
    ) -> Tuple[str, int, float]:
        from PIL import Image

        assistant_prefix = render_assistant_prefix(
            messages, self.assistant_prefix, self.assistant_prefix_template
        )
        conversation = adapt_messages_for_family(
            messages, self.family, assistant_prefix=assistant_prefix
        )
        pil_images = []
        for image_path in conversation[0]["images"]:
            with Image.open(Path(image_path)) as image:
                pil_images.append(
                    resize_image_to_pixel_budget(
                        image.convert("RGB"), self.max_image_pixels
                    )
                )
        prepared = self.processor(
            conversations=conversation,
            images=pil_images,
            force_batchify=True,
            system_prompt="\n".join(
                part
                for part in (extract_system_prompt(messages), self.constraint_prompt)
                if part
            ),
        ).to(next(self.model.parameters()).device)
        started = time.perf_counter()
        with self.torch.inference_mode():
            inputs_embeds = self.model.prepare_inputs_embeds(**prepared)
            language_model = getattr(
                self.model, "language_model", getattr(self.model, "language", None)
            )
            if language_model is None:
                raise AttributeError("DeepSeek-VL2 model has no language decoder")
            generation_kwargs: Dict[str, Any] = {}
            if self.json_schema_constraint:
                from lmformatenforcer import JsonSchemaParser
                from lmformatenforcer.integrations.transformers import (
                    build_transformers_prefix_allowed_tokens_fn,
                )

                parser = JsonSchemaParser(
                    agent_request_json_schema(request_id_from_messages(messages))
                )
                allowed_tokens_fn = build_transformers_prefix_allowed_tokens_fn(
                    self.lmfe_tokenizer_data, parser
                )
                generation_kwargs["logits_processor"] = [
                    AllowedTokensLogitsProcessor(allowed_tokens_fn, self.tokenizer)
                ]
            generated = language_model.generate(
                inputs_embeds=inputs_embeds,
                attention_mask=prepared.attention_mask,
                pad_token_id=self.tokenizer.eos_token_id,
                bos_token_id=self.tokenizer.bos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                use_cache=True,
                **generation_kwargs,
            )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        token_count = int(generated.shape[1])
        text = self.tokenizer.decode(
            generated[0].detach().cpu().tolist(), skip_special_tokens=True
        ).strip()
        if assistant_prefix and not text.startswith(assistant_prefix):
            text = assistant_prefix + text
        return text, token_count, elapsed_ms
