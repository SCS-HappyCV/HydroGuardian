from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from .schema import (
    DEFAULT_EVIDENCE,
    HydrologicalProgram,
    OperatorizedSpatialProgram,
    ProgramBundle,
    ProgramCandidate,
    ProgramLike,
    ProgramStep,
    RelationClause,
    canonicalize_attribute_name,
    canonicalize_label_name,
    canonicalize_relation_type,
    ensure_negative_priors,
    first_available_target,
    label_ids_from_names,
    label_names_from_ids,
    merge_evidence,
    operatorized_program_from_field_program,
    program_from_dict,
    unique_list,
)

RELATION_EVIDENCE = {
    "near": ["xy_distance", "ortho_context"],
    "adjacent": ["xy_distance", "ortho_context"],
    "along": ["xy_distance", "ortho_edge"],
    "above": ["z_norm", "slope"],
    "below": ["z_norm", "slope"],
}

OPENAI_PROGRAM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "target": {"type": "string"},
        "attributes": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
        "relations": {
            "type": "array",
            "default": [],
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {"type": "string"},
                    "reference": {"type": "string"},
                    "distance_m": {"type": ["number", "null"]},
                    "margin_m": {"type": ["number", "null"]},
                },
                "required": ["type", "reference", "distance_m", "margin_m"],
            },
        },
        "negatives": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
    },
    "required": ["target", "attributes", "relations", "negatives", "evidence"],
}

OPENAI_OPERATOR_PROGRAM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "program_version": {"type": "string"},
        "target": {"type": "string"},
        "steps": {
            "type": "array",
            "default": [],
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "op": {"type": "string"},
                    "input": {"type": ["string", "null"]},
                    "inputs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                    "label": {"type": ["string", "null"]},
                    "attribute": {"type": ["string", "null"]},
                    "relation": {"type": ["string", "null"]},
                    "reference_label": {"type": ["string", "null"]},
                    "distance_m": {"type": ["number", "null"]},
                    "margin_m": {"type": ["number", "null"]},
                    "logic": {"type": ["string", "null"]},
                },
                "required": [
                    "id",
                    "op",
                    "input",
                    "inputs",
                    "label",
                    "attribute",
                    "relation",
                    "reference_label",
                    "distance_m",
                    "margin_m",
                    "logic",
                ],
            },
        },
        "output_step_id": {"type": "string"},
        "negatives": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
    },
    "required": ["program_version", "target", "steps", "output_step_id", "negatives", "evidence"],
}

OPENAI_COMPILER_PROMPT = """You are a compiler that converts hydrological remote-sensing segmentation queries into a structured program.

Return only fields supported by the schema.

Rules:
- target must be a single class from the allowed class names.
- attributes should use canonical attribute names only.
- relations should use canonical relation names only.
- reference must be a class name, not free text.
- If a distance or margin is unknown, set it to null.
- negatives should list confusing classes that should be suppressed.
- evidence should be a short list chosen from likely signals such as z_norm, slope, xy_distance, ortho_context, ortho_edge, ortho_texture, geometry.
- Do not invent classes outside the allowed vocabulary.
- If the query is ambiguous, choose the most plausible hydrological interpretation and keep the structure minimal.
"""

OPENAI_OPERATOR_COMPILER_PROMPT = """You are a compiler that converts hydrological remote-sensing segmentation queries into an executable spatial program.

Return only fields supported by the schema.

Rules:
- target must be a single class from the allowed class names.
- Build a step-by-step operator program using only select, filter, relate, exclude, and optional compose.
- Use canonical attribute names and canonical relation names only.
- reference_label must be a class name, not free text.
- If a distance or margin is unknown, set it to null.
- output_step_id must match the final step id.
- negatives should list confusing classes that should be suppressed.
- evidence should be a short list chosen from likely signals such as z_norm, slope, xy_distance, ortho_context, ortho_edge, ortho_texture, geometry.
- Do not invent classes or operators outside the allowed vocabulary.
- Keep the program minimal and executable.
"""


@dataclass
class QueryCompilerConfig:
    backend: str = "rule"
    enable_default_negatives: bool = True
    default_near_distance_m: float = 3.0
    default_along_distance_m: float = 4.0
    default_above_margin_m: float = 0.2
    infer_attributes_from_text: bool = True
    infer_relations_from_text: bool = True
    attach_scene_metadata: bool = False
    scene_metadata_keys: Sequence[str] = field(default_factory=tuple)
    use_scene_task_hints: bool = False
    program_schema_mode: str = "field"
    program_version: str = "v3_operatorized"
    relation_distance_overrides: Dict[str, float] = field(
        default_factory=lambda: {
            "near": 3.0,
            "adjacent": 3.0,
            "along": 4.0,
        }
    )
    openai_model: str = "gpt-5.5"
    openai_reasoning_effort: Optional[str] = "low"
    openai_timeout_seconds: float = 60.0
    openai_store: bool = False
    openai_max_output_tokens: int = 300
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_api_mode: str = "auto"
    openai_disable_thinking: bool = False
    openai_organization: Optional[str] = None
    openai_project: Optional[str] = None
    openai_api_key_env: str = "OPENAI_API_KEY"
    openai_base_url_env: str = "OPENAI_BASE_URL"
    openai_organization_env: str = "OPENAI_ORG_ID"
    openai_project_env: str = "OPENAI_PROJECT_ID"
    openai_prompt: str = OPENAI_COMPILER_PROMPT
    openai_operator_prompt: str = OPENAI_OPERATOR_COMPILER_PROMPT
    fallback_to_rule_on_error: bool = True
    num_program_candidates: int = 3
    enable_program_repair: bool = True
    enable_no_target_option: bool = False


class HydrologicalQueryCompiler:
    def __init__(self, config: Optional[QueryCompilerConfig] = None) -> None:
        self.config = config or QueryCompilerConfig()
        self._openai_client = None

    def _program_metadata_context(self, scene_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not scene_context or not self.config.attach_scene_metadata:
            return {}
        allowed_keys = [str(key) for key in self.config.scene_metadata_keys]
        if not allowed_keys:
            return {}
        return {
            key: scene_context[key]
            for key in allowed_keys
            if key in scene_context and scene_context[key] is not None
        }

    def _build_no_target_candidate_program(
        self,
        text: str,
        scene_context: Optional[Dict[str, Any]] = None,
    ) -> ProgramLike:
        metadata: Dict[str, Any] = {
            "no_target_candidate": True,
            "compiler": "explicit_no_target",
            "program_schema_mode": self.config.program_schema_mode,
        }
        metadata.update(self._program_metadata_context(scene_context))
        if self.config.program_schema_mode == "operatorized":
            return OperatorizedSpatialProgram(
                program_version=self.config.program_version,
                target="others",
                target_label_ids=[],
                attributes=[],
                relations=[],
                negatives=[],
                negative_label_ids=[],
                steps=[],
                output_step_id="",
                evidence=[],
                metadata=metadata,
                source_text=text,
            )
        return HydrologicalProgram(
            target="others",
            target_label_ids=[],
            attributes=[],
            relations=[],
            negatives=[],
            negative_label_ids=[],
            evidence=[],
            metadata=metadata,
            source_text=text,
        )

    def _no_target_candidate_score(self, scene_context: Optional[Dict[str, Any]] = None) -> float:
        return 0.25

    def _candidate_noise_type(
        self,
        proposal_source: str,
        program: ProgramLike,
        scene_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        repaired = bool(dict(program.metadata).get("sanitizer_applied", False))
        if proposal_source == "explicit_no_target":
            return "explicit_no_target"
        if proposal_source == "sample":
            return "sample_aware_repair" if repaired else "sample_aware"
        if proposal_source == "normalized":
            return "normalized_repair" if repaired else "normalized"
        if proposal_source == "rule":
            return "rule_repair" if repaired else "rule_fallback"
        if proposal_source == "openai":
            return "openai_repair" if repaired else "openai_compiler"
        return "unknown"

    def _candidate_confidence(
        self,
        proposal_source: str,
        proposal_score: float,
        program: ProgramLike,
        scene_context: Optional[Dict[str, Any]] = None,
    ) -> float:
        repaired = bool(dict(program.metadata).get("sanitizer_applied", False))
        confidence = float(proposal_score)
        if proposal_source == "rule":
            confidence *= 0.85
        elif proposal_source == "normalized":
            confidence *= 0.90
        elif proposal_source == "sample":
            confidence *= 0.95
        if repaired:
            confidence *= 0.92
        if proposal_source == "explicit_no_target":
            confidence = min(confidence, 0.25)
        return max(0.0, min(float(confidence), 1.0))

    def _maybe_operatorize_program(self, program: ProgramLike) -> ProgramLike:
        if isinstance(program, OperatorizedSpatialProgram):
            return program
        if self.config.program_schema_mode == "operatorized":
            return operatorized_program_from_field_program(program, program_version=self.config.program_version).with_metadata(
                program_schema_mode="operatorized"
            )
        return program

    def compile_text(self, text: str, scene_context: Optional[Dict[str, Any]] = None) -> ProgramLike:
        if self.config.backend == "openai":
            try:
                program = self._compile_text_openai(text, scene_context=scene_context)
            except Exception:
                if not self.config.fallback_to_rule_on_error:
                    raise
                program = self._compile_text_rule(text, scene_context=scene_context)
        else:
            program = self._compile_text_rule(text, scene_context=scene_context)
        return self._sanitize_program(program, scene_context=scene_context)

    def compile_text_bundle(self, text: str, scene_context: Optional[Dict[str, Any]] = None) -> ProgramBundle:
        candidates: List[ProgramCandidate] = []
        seen_payloads = set()

        def add_candidate(program: ProgramLike, proposal_source: str, proposal_score: float, rationale: str = "") -> None:
            sanitized = self._sanitize_program(program, scene_context=scene_context)
            payload = json.dumps(sanitized.to_dict(), ensure_ascii=False, sort_keys=True)
            if payload in seen_payloads:
                return
            seen_payloads.add(payload)
            noise_type = self._candidate_noise_type(proposal_source, sanitized, scene_context=scene_context)
            compiler_confidence = self._candidate_confidence(
                proposal_source,
                proposal_score,
                sanitized,
                scene_context=scene_context,
            )
            candidate_metadata = {"program_schema_mode": self.config.program_schema_mode}
            if bool(dict(sanitized.metadata).get("no_target_candidate", False)):
                candidate_metadata["no_target_candidate"] = True
            candidates.append(
                ProgramCandidate(
                    candidate_id=f"c{len(candidates)}",
                    program=sanitized,
                    proposal_score=float(proposal_score),
                    proposal_source=proposal_source,
                    noise_type=noise_type,
                    compiler_confidence=compiler_confidence,
                    rationale=rationale,
                    is_repaired=bool(dict(sanitized.metadata).get("sanitizer_applied", False)),
                    metadata=candidate_metadata,
                )
            )

        if self.config.backend == "openai":
            try:
                add_candidate(
                    self._compile_text_openai(text, scene_context=scene_context),
                    proposal_source="openai",
                    proposal_score=1.0,
                    rationale="Primary OpenAI-compatible compiler output.",
                )
            except Exception:
                if not self.config.fallback_to_rule_on_error:
                    raise
        add_candidate(
            self._compile_text_rule(text, scene_context=scene_context),
            proposal_source="rule",
            proposal_score=0.7 if self.config.backend == "openai" else 1.0,
            rationale="Rule-based fallback candidate.",
        )
        if candidates:
            normalized_candidate = self._normalized_bundle_variant(candidates[0].program)
            if normalized_candidate is not None:
                add_candidate(
                    normalized_candidate,
                    proposal_source="normalized",
                    proposal_score=max(candidates[0].proposal_score - 0.1, 0.0),
                    rationale="Deterministic normalized operatorized variant.",
                )
        if self.config.enable_no_target_option:
            add_candidate(
                self._build_no_target_candidate_program(text, scene_context=scene_context),
                proposal_source="explicit_no_target",
                proposal_score=self._no_target_candidate_score(scene_context=scene_context),
                rationale="Explicit abstention / no-target candidate.",
            )
        candidates.sort(
            key=lambda candidate: (float(candidate.proposal_score), float(candidate.compiler_confidence)),
            reverse=True,
        )
        max_candidates = max(int(self.config.num_program_candidates), 1)
        if len(candidates) > max_candidates:
            no_target_candidates = [
                candidate for candidate in candidates if bool(dict(candidate.metadata).get("no_target_candidate", False))
            ]
            regular_candidates = [
                candidate for candidate in candidates if not bool(dict(candidate.metadata).get("no_target_candidate", False))
            ]
            if no_target_candidates and max_candidates > 1:
                reserved_regular = max(max_candidates - 1, 0)
                candidates = regular_candidates[:reserved_regular] + no_target_candidates[:1]
            else:
                candidates = candidates[:max_candidates]
        if not candidates:
            raise ValueError("Compiler failed to build any program candidates.")
        return ProgramBundle(
            source_text=text,
            candidates=candidates,
            selected_candidate_id=candidates[0].candidate_id,
            metadata={
                "compiler_backend": self.config.backend,
                "program_schema_mode": self.config.program_schema_mode,
                "num_candidates": len(candidates),
            },
        )

    def _compile_text_rule(self, text: str, scene_context: Optional[Dict[str, Any]] = None) -> ProgramLike:
        normalized = self._normalize_text(text)
        target_name = self._infer_target_name(normalized)
        attributes = self._infer_attributes(normalized) if self.config.infer_attributes_from_text else []
        relations = self._infer_relations(normalized) if self.config.infer_relations_from_text else []
        negatives = self._infer_negatives(normalized)
        if self.config.enable_default_negatives and target_name is not None:
            negatives = ensure_negative_priors(target_name, negatives)

        target_label_ids = label_ids_from_names([target_name]) if target_name is not None else []
        target = target_name or first_available_target(target_label_ids)
        negative_label_ids = label_ids_from_names(negatives)
        evidence = merge_evidence(attributes, relations)

        metadata = self._program_metadata_context(scene_context)

        program = HydrologicalProgram(
            target=target,
            target_label_ids=target_label_ids,
            attributes=attributes,
            relations=relations,
            negatives=negatives,
            negative_label_ids=negative_label_ids,
            evidence=evidence,
            metadata=metadata,
            source_text=text,
        )
        return self._maybe_operatorize_program(program)

    def _normalized_bundle_variant(self, program: ProgramLike) -> Optional[ProgramLike]:
        if not isinstance(program, OperatorizedSpatialProgram):
            return None
        normalized = operatorized_program_from_field_program(
            program.to_field_program(),
            program_version=self.config.program_version,
        ).with_metadata(**program.metadata)
        if normalized.to_dict() == program.to_dict():
            return None
        return normalized

    def _compile_text_openai(self, text: str, scene_context: Optional[Dict[str, Any]] = None) -> ProgramLike:
        client = self._get_openai_client()
        mode = str(self.config.openai_api_mode).lower().strip()
        if mode not in {"auto", "responses", "chat_completions"}:
            raise ValueError(
                f"Unsupported openai_api_mode={self.config.openai_api_mode!r}, "
                "expected 'auto', 'responses', or 'chat_completions'."
            )

        response = None
        request_mode = mode
        if mode in {"auto", "responses"}:
            try:
                request_kwargs = self._build_openai_responses_request(text, scene_context=scene_context)
                response = client.responses.create(**request_kwargs)
                request_mode = "responses"
            except Exception as exc:
                if mode == "responses" or not self._should_fallback_to_chat_completions(exc):
                    raise
                response = None
                request_mode = "chat_completions"

        if response is None:
            request_kwargs = self._build_openai_chat_completions_request(text, scene_context=scene_context)
            response = client.chat.completions.create(**request_kwargs)
            request_mode = "chat_completions"

        output_text = self._extract_text_from_response(response)
        if not output_text:
            preview = self._response_preview(response)
            diagnosis = self._response_empty_text_diagnosis(response)
            raise ValueError(
                f"OpenAI compiler returned an empty textual response. {diagnosis} "
                f"Response preview: {preview}"
            )
        payload = self._parse_openai_payload_text(output_text)
        if self.config.program_schema_mode == "operatorized":
            program = self._operator_program_from_openai_payload(payload, source_text=text, scene_context=scene_context)
        else:
            program = self._program_from_openai_payload(payload, source_text=text, scene_context=scene_context)
        metadata = dict(program.metadata)
        metadata.update(
            {
                "compiler": "openai",
                "openai_model": self.config.openai_model,
                "openai_api_mode": request_mode,
                "openai_response_id": getattr(response, "id", None),
            }
        )
        return program.with_metadata(**metadata)

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @staticmethod
    def _extract_text_value(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        if isinstance(value, dict):
            text_value = value.get("text")
            if isinstance(text_value, str):
                stripped = text_value.strip()
                return stripped or None
            if isinstance(text_value, dict):
                candidate = text_value.get("value")
                if isinstance(candidate, str):
                    stripped = candidate.strip()
                    return stripped or None
            for key in ("value", "content"):
                candidate = value.get(key)
                if isinstance(candidate, str):
                    stripped = candidate.strip()
                    if stripped:
                        return stripped
        return None

    @staticmethod
    def _response_to_dict(response: Any) -> Dict[str, Any]:
        if isinstance(response, dict):
            return response
        for attr in ("model_dump", "dict"):
            method = getattr(response, attr, None)
            if callable(method):
                try:
                    payload = method()
                    if isinstance(payload, dict):
                        return payload
                except Exception:
                    pass
        raw_dict = getattr(response, "__dict__", None)
        if isinstance(raw_dict, dict):
            return raw_dict
        return {}

    def _extract_text_from_response(self, response: Any) -> Optional[str]:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        payload = self._response_to_dict(response)
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()

        for item in self._as_list(payload.get("output")):
            if not isinstance(item, dict):
                continue
            for content in self._as_list(item.get("content")):
                text_value = self._extract_text_value(content)
                if text_value:
                    return text_value

        for choice in self._as_list(payload.get("choices")):
            if not isinstance(choice, dict):
                continue
            message = choice.get("message", {})
            if isinstance(message, dict):
                message_content = message.get("content")
                if isinstance(message_content, str) and message_content.strip():
                    return message_content.strip()
                for content in self._as_list(message_content):
                    text_value = self._extract_text_value(content)
                    if text_value:
                        return text_value
            text_value = self._extract_text_value(choice)
            if text_value:
                return text_value
        return None

    def _response_empty_text_diagnosis(self, response: Any) -> str:
        payload = self._response_to_dict(response)
        for choice in self._as_list(payload.get("choices")):
            if not isinstance(choice, dict):
                continue
            finish_reason = choice.get("finish_reason")
            message = choice.get("message", {})
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            reasoning_content = (
                message.get("reasoning_content")
                or message.get("reasoning")
                or message.get("reasoningContent")
            )
            if finish_reason == "length" and (content == "" or content is None) and reasoning_content:
                return (
                    "The backend stopped with finish_reason='length' after producing reasoning content but before "
                    "emitting the final JSON answer. Increase openai_max_output_tokens, keep openai_api_mode="
                    "'chat_completions' for this local backend, and use a concise non-thinking prompt."
                )
        return "The backend returned no usable textual content."

    def _response_preview(self, response: Any) -> str:
        payload = self._response_to_dict(response)
        if payload:
            try:
                text = json.dumps(payload, ensure_ascii=False)
                return text[:500].replace("\n", "\\n")
            except Exception:
                pass
        return str(response)[:500].replace("\n", "\\n")

    @staticmethod
    def _clean_openai_output_text(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

    @staticmethod
    def _parse_scalar_text(text: str) -> Any:
        value = text.strip().rstrip(",")
        if not value:
            return None
        lowered = value.lower()
        if lowered in {"null", "none"}:
            return None
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if value in {"[]", "[", "]"}:
            return []
        if value in {"{}", "{", "}"}:
            return {}
        if (value.startswith("[") and value.endswith("]")) or (value.startswith("{") and value.endswith("}")):
            try:
                return json.loads(value)
            except Exception:
                try:
                    return ast.literal_eval(value)
                except Exception:
                    pass
        if re.fullmatch(r"[-+]?\d+", value):
            try:
                return int(value)
            except Exception:
                pass
        if re.fullmatch(r"[-+]?\d*\.\d+", value):
            try:
                return float(value)
            except Exception:
                pass
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        return value

    def _parse_key_value_payload_text(self, text: str) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "target": None,
            "attributes": [],
            "relations": [],
            "negatives": [],
            "evidence": [],
        }
        current_relation: Dict[str, Any] = {}
        seen_any = False

        def flush_relation() -> None:
            nonlocal current_relation
            if not current_relation:
                return
            if current_relation.get("type") is None and current_relation.get("reference") is None:
                current_relation = {}
                return
            payload["relations"].append(
                {
                    "type": current_relation.get("type"),
                    "reference": current_relation.get("reference"),
                    "distance_m": current_relation.get("distance_m"),
                    "margin_m": current_relation.get("margin_m"),
                }
            )
            current_relation = {}

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            seen_any = True
            if line.startswith("- "):
                line = line[2:].strip()
            key, value_text = line.split(":", 1)
            key = key.strip().lower()
            value = self._parse_scalar_text(value_text)

            if key == "target":
                payload["target"] = value
                continue
            if key in {"attributes", "negatives", "evidence"}:
                if isinstance(value, list):
                    payload[key] = value
                elif value is None:
                    payload[key] = []
                else:
                    payload[key] = [value]
                continue
            if key == "relations":
                if isinstance(value, list):
                    flush_relation()
                    payload["relations"] = value
                elif isinstance(value, dict):
                    flush_relation()
                    payload["relations"] = [value]
                elif value in (None, []):
                    flush_relation()
                else:
                    current_relation["type"] = value
                continue
            if key in {"type", "relation_type"}:
                current_relation["type"] = value
                continue
            if key == "reference":
                current_relation["reference"] = value
                continue
            if key in {"distance", "distance_m"}:
                current_relation["distance_m"] = value
                continue
            if key in {"margin", "margin_m"}:
                current_relation["margin_m"] = value
                continue

        flush_relation()
        if not seen_any:
            return None
        if payload["target"] is None and not payload["relations"] and not payload["attributes"] and not payload["negatives"]:
            return None
        return payload

    def _parse_openai_payload_text(self, output_text: str) -> Dict[str, Any]:
        cleaned = self._clean_openai_output_text(output_text)
        if not cleaned:
            raise ValueError("OpenAI compiler returned only whitespace or empty fenced text.")

        try:
            payload = json.loads(cleaned)
            if not isinstance(payload, dict):
                raise TypeError(f"Expected JSON object, got {type(payload).__name__}.")
            return payload
        except Exception:
            pass

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            candidate = cleaned[start : end + 1]
            try:
                payload = json.loads(candidate)
                if not isinstance(payload, dict):
                    raise TypeError(f"Expected JSON object, got {type(payload).__name__}.")
                return payload
            except Exception:
                pass

        kv_payload = self._parse_key_value_payload_text(cleaned)
        if kv_payload is not None:
            return kv_payload

        preview = cleaned[:500].replace("\n", "\\n")
        raise ValueError(f"Failed to parse compiler JSON response. Raw output preview: {preview}")

    def _get_openai_client(self):
        if self._openai_client is not None:
            return self._openai_client

        try:
            from openai import OpenAI
        except Exception as exc:
            raise ImportError(
                "OpenAI compiler backend requires the official `openai` Python package. "
                "Install it with `pip install openai` in the active environment."
            ) from exc

        base_url = self.config.openai_base_url or os.getenv(self.config.openai_base_url_env)
        api_key = self.config.openai_api_key or os.getenv(self.config.openai_api_key_env)
        if not api_key and self._is_local_openai_base_url(base_url):
            api_key = "EMPTY"
        if not api_key:
            raise EnvironmentError(
                f"Missing OpenAI API key. Set environment variable {self.config.openai_api_key_env}."
            )

        kwargs: Dict[str, Any] = {
            "api_key": api_key,
            "timeout": float(self.config.openai_timeout_seconds),
        }
        organization = self.config.openai_organization or os.getenv(self.config.openai_organization_env)
        project = self.config.openai_project or os.getenv(self.config.openai_project_env)
        if base_url:
            kwargs["base_url"] = self._normalize_openai_base_url(base_url)
        if organization:
            kwargs["organization"] = organization
        if project:
            kwargs["project"] = project
        self._openai_client = OpenAI(**kwargs)
        return self._openai_client

    @staticmethod
    def _is_local_openai_base_url(base_url: Optional[str]) -> bool:
        if not base_url:
            return False
        try:
            parsed = urlparse(base_url)
        except Exception:
            return False
        hostname = (parsed.hostname or "").lower()
        return hostname in {"127.0.0.1", "localhost", "0.0.0.0"}

    @staticmethod
    def _normalize_openai_base_url(base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        for suffix in ("/chat/completions", "/responses", "/completions"):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized

    @staticmethod
    def _should_fallback_to_chat_completions(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code in {404, 405, 501}:
            return True
        message = str(exc).lower()
        return any(token in message for token in ["404", "not found", "responses", "/responses"])

    def _build_openai_prompt_context(self, text: str, scene_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        scene_lines = []
        metadata_context = self._program_metadata_context(scene_context)
        if metadata_context:
            for key, value in metadata_context.items():
                scene_lines.append(f"- {key}: {value}")
        class_names = ", ".join(label_names_from_ids(range(15)))
        allowed_attributes = ", ".join(sorted(set([
            "thin",
            "linear",
            "flat",
            "steep",
            "low_elevation",
            "high_elevation",
            "water_related",
            "vegetated",
            "bare_ground",
            "built",
        ])))
        allowed_relations = ", ".join(sorted(set(RELATION_EVIDENCE.keys())))
        input_text = (
            f"Allowed classes: {class_names}\n"
            f"Allowed attributes: {allowed_attributes}\n"
            f"Allowed relations: {allowed_relations}\n"
            f"Scene context:\n{chr(10).join(scene_lines) if scene_lines else '- none'}\n"
            f"User query:\n{text}"
        )
        if self.config.program_schema_mode == "operatorized":
            instructions = self.config.openai_operator_prompt
            schema = OPENAI_OPERATOR_PROGRAM_SCHEMA
        else:
            instructions = self.config.openai_prompt
            schema = OPENAI_PROGRAM_SCHEMA
        return {
            "instructions": instructions,
            "schema": schema,
            "input_text": input_text,
        }

    def _build_openai_responses_request(self, text: str, scene_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        prompt_context = self._build_openai_prompt_context(text, scene_context=scene_context)
        request: Dict[str, Any] = {
            "model": self.config.openai_model,
            "instructions": prompt_context["instructions"],
            "input": prompt_context["input_text"],
            "store": bool(self.config.openai_store),
            "max_output_tokens": int(self.config.openai_max_output_tokens),
            "text": {
                "format": {
                    "type": "json_schema",
                    "strict": True,
                    "schema": prompt_context["schema"],
                }
            },
        }
        if self.config.openai_reasoning_effort:
            request["reasoning"] = {"effort": self.config.openai_reasoning_effort}
        return request

    def _build_openai_chat_completions_request(self, text: str, scene_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        prompt_context = self._build_openai_prompt_context(text, scene_context=scene_context)
        if self.config.program_schema_mode == "operatorized":
            schema_brief = (
                '{"program_version":"v3_operatorized","target":"<class>",'
                '"steps":[{"id":"s1","op":"select","input":null,"inputs":[],"label":"<class>",'
                '"attribute":null,"relation":null,"reference_label":null,"distance_m":null,'
                '"margin_m":null,"logic":null}],"output_step_id":"<step_id>",'
                '"negatives":["<class>"],"evidence":["geometry"]}'
            )
        else:
            schema_brief = (
                '{"target":"<class>","attributes":["<attr>"],'
                '"relations":[{"type":"near","reference":"<class>","distance_m":3.0,"margin_m":null}],'
                '"negatives":["<class>"],"evidence":["geometry"]}'
            )
        system_prompt = (
            f"{prompt_context['instructions']}\n\n"
            "Return compact JSON only. Do not output reasoning, markdown fences, explanations, or any text before or after the JSON.\n"
            "Do not think step by step in the answer. Emit the final JSON directly.\n"
            f"Target JSON shape example:\n{schema_brief}"
        )
        request: Dict[str, Any] = {
            "model": self.config.openai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_context["input_text"]},
            ],
            "temperature": 0.0,
            "max_tokens": int(self.config.openai_max_output_tokens),
        }
        if self.config.openai_disable_thinking:
            request["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": False},
            }
        return request

    def _operator_program_from_field_program(
        self,
        program: HydrologicalProgram,
    ) -> OperatorizedSpatialProgram:
        operator_program = operatorized_program_from_field_program(
            program,
            program_version=self.config.program_version,
        )
        return operator_program.with_metadata(**program.metadata)

    def _operator_program_from_openai_payload(
        self,
        payload: Dict[str, Any],
        source_text: str,
        scene_context: Optional[Dict[str, Any]] = None,
    ) -> OperatorizedSpatialProgram:
        if "steps" not in payload:
            return self._operator_program_from_field_program(
                self._program_from_openai_payload(payload, source_text=source_text, scene_context=scene_context)
            )

        target_name = canonicalize_label_name(str(payload.get("target", "others"))) or "others"
        target_label_ids = label_ids_from_names([target_name])
        steps: List[ProgramStep] = []
        attributes: List[str] = []
        relations: List[RelationClause] = []
        negatives: List[str] = []

        for step_payload in self._as_list(payload.get("steps")):
            if not isinstance(step_payload, dict):
                continue
            op = str(step_payload.get("op", "")).strip().lower()
            label_name = step_payload.get("label")
            canonical_label = canonicalize_label_name(str(label_name)) if label_name is not None else None
            attribute_name = step_payload.get("attribute")
            canonical_attr = canonicalize_attribute_name(str(attribute_name)) if attribute_name is not None else None
            relation_name = step_payload.get("relation")
            canonical_relation = canonicalize_relation_type(str(relation_name)) if relation_name is not None else None
            reference_label = step_payload.get("reference_label")
            canonical_reference = (
                canonicalize_label_name(str(reference_label)) if reference_label is not None else None
            )

            label_ids = [int(idx) for idx in step_payload.get("label_ids", [])]
            if not label_ids and canonical_label is not None:
                label_ids = label_ids_from_names([canonical_label])
            reference_label_ids = [int(idx) for idx in step_payload.get("reference_label_ids", [])]
            if not reference_label_ids and canonical_reference is not None:
                reference_label_ids = label_ids_from_names([canonical_reference])

            evidence = [str(item) for item in step_payload.get("evidence", [])]
            if canonical_attr is not None:
                for token in DEFAULT_EVIDENCE.get(canonical_attr, []):
                    if token not in evidence:
                        evidence.append(token)
            if canonical_relation is not None:
                for token in RELATION_EVIDENCE.get(canonical_relation, []):
                    if token not in evidence:
                        evidence.append(token)

            step = ProgramStep(
                id=str(step_payload.get("id", f"s{len(steps) + 1}")),
                op=op,
                input=None if step_payload.get("input") is None else str(step_payload.get("input")),
                inputs=[str(item) for item in step_payload.get("inputs", [])],
                label=canonical_label,
                label_ids=label_ids,
                attribute=canonical_attr,
                relation=canonical_relation,
                reference_label=canonical_reference,
                reference_label_ids=reference_label_ids,
                distance_m=step_payload.get("distance_m"),
                margin_m=step_payload.get("margin_m"),
                logic=None if step_payload.get("logic") is None else str(step_payload.get("logic")).upper(),
                evidence=evidence,
            )
            steps.append(step)

            if step.op == "filter" and step.attribute is not None and step.attribute not in attributes:
                attributes.append(step.attribute)
            if step.op == "relate" and step.relation is not None and step.reference_label is not None:
                relations.append(
                    RelationClause(
                        type=step.relation,
                        reference=step.reference_label,
                        reference_label_ids=list(step.reference_label_ids),
                        distance_m=step.distance_m,
                        margin_m=step.margin_m,
                        evidence=list(step.evidence),
                    )
                )
            if step.op == "exclude" and step.label is not None and step.label not in negatives:
                negatives.append(step.label)

        if target_name == "others":
            for step in steps:
                if step.op == "select" and step.label is not None:
                    target_name = step.label
                    target_label_ids = list(step.label_ids) or label_ids_from_names([target_name])
                    break

        if self.config.enable_default_negatives:
            negatives = ensure_negative_priors(target_name, negatives)
        evidence = merge_evidence(attributes, relations)
        for item in self._as_list(payload.get("evidence")):
            value = str(item).strip()
            if value and value not in evidence:
                evidence.append(value)

        metadata = self._program_metadata_context(scene_context)
        output_step_id = str(payload.get("output_step_id", payload.get("output", steps[-1].id if steps else "")))
        return OperatorizedSpatialProgram(
            program_version=str(payload.get("program_version", self.config.program_version)),
            target=target_name,
            target_label_ids=target_label_ids,
            attributes=unique_list(attributes),
            relations=relations,
            negatives=unique_list(negatives),
            negative_label_ids=label_ids_from_names(negatives),
            steps=steps,
            output_step_id=output_step_id,
            evidence=evidence,
            metadata=metadata,
            source_text=source_text,
        )

    def _program_from_openai_payload(
        self,
        payload: Dict[str, Any],
        source_text: str,
        scene_context: Optional[Dict[str, Any]] = None,
    ) -> HydrologicalProgram:
        target_name = canonicalize_label_name(str(payload.get("target", "others"))) or "others"
        target_label_ids = label_ids_from_names([target_name])
        attributes = []
        for item in self._as_list(payload.get("attributes")):
            canonical = canonicalize_attribute_name(str(item))
            if canonical is not None:
                attributes.append(canonical)
        relations = []
        for relation_payload in self._as_list(payload.get("relations")):
            if not isinstance(relation_payload, dict):
                continue
            relation_type = canonicalize_relation_type(str(relation_payload.get("type", "near"))) or "near"
            reference_name = canonicalize_label_name(str(relation_payload.get("reference", "")))
            if reference_name is None:
                continue
            relations.append(
                RelationClause(
                    type=relation_type,
                    reference=reference_name,
                    reference_label_ids=label_ids_from_names([reference_name]),
                    distance_m=relation_payload.get("distance_m"),
                    margin_m=relation_payload.get("margin_m"),
                    evidence=list(RELATION_EVIDENCE.get(relation_type, [])),
                )
            )
        negatives = []
        for item in self._as_list(payload.get("negatives")):
            normalized = canonicalize_label_name(str(item))
            if normalized is not None:
                negatives.append(normalized)
        if self.config.enable_default_negatives:
            negatives = ensure_negative_priors(target_name, negatives)
        evidence = merge_evidence(attributes, relations)
        for item in self._as_list(payload.get("evidence")):
            value = str(item).strip()
            if value and value not in evidence:
                evidence.append(value)
        metadata = self._program_metadata_context(scene_context)
        return HydrologicalProgram(
            target=target_name,
            target_label_ids=target_label_ids,
            attributes=unique_list(attributes),
            relations=relations,
            negatives=unique_list(negatives),
            negative_label_ids=label_ids_from_names(negatives),
            evidence=evidence,
            metadata=metadata,
            source_text=source_text,
        )

    def compile_sample(self, sample: Dict[str, Any]) -> ProgramLike:
        parsed = self.compile_text(
            sample["text"],
            scene_context=None,
        )

        target_label_ids = self._sample_target_label_ids(sample)
        target_name = first_available_target(target_label_ids) if target_label_ids else parsed.target

        sample_attributes = []
        for attribute in sample.get("attributes", []):
            canonical = canonicalize_attribute_name(str(attribute))
            if canonical is not None:
                sample_attributes.append(canonical)
        attributes = unique_list(sample_attributes or parsed.attributes)

        relations = self._sample_relations(sample)
        if not relations:
            relations = parsed.relations

        negatives = parsed.negatives
        if self.config.enable_default_negatives:
            negatives = ensure_negative_priors(target_name, negatives)

        evidence = merge_evidence(attributes, relations)
        negative_label_ids = label_ids_from_names(negatives)
        metadata = dict(parsed.metadata)
        metadata["compiler"] = "sample-aware"

        program = HydrologicalProgram(
            target=target_name,
            target_label_ids=target_label_ids or parsed.target_label_ids,
            attributes=attributes,
            relations=relations,
            negatives=negatives,
            negative_label_ids=negative_label_ids,
            evidence=evidence,
            metadata=metadata,
            source_text=sample["text"],
        )
        return self._maybe_operatorize_program(program)

    def compile_sample_bundle(self, sample: Dict[str, Any]) -> ProgramBundle:
        bundle = self.compile_text_bundle(
            sample["text"],
            scene_context=None,
        )
        sample_program = self.compile_sample(sample)
        sample_candidate = ProgramCandidate(
            candidate_id=f"c{len(bundle.candidates)}",
            program=self._sanitize_program(sample_program, scene_context=None),
            proposal_score=0.95,
            proposal_source="sample",
            noise_type=self._candidate_noise_type("sample", sample_program, scene_context=None),
            compiler_confidence=0.95,
            rationale="Sample-aware program candidate.",
            is_repaired=bool(dict(sample_program.metadata).get("sanitizer_applied", False)),
        )
        existing = {json.dumps(candidate.program.to_dict(), ensure_ascii=False, sort_keys=True) for candidate in bundle.candidates}
        payload = json.dumps(sample_candidate.program.to_dict(), ensure_ascii=False, sort_keys=True)
        if payload not in existing and len(bundle.candidates) < max(int(self.config.num_program_candidates), 1):
            bundle.candidates.append(sample_candidate)
        bundle.selected_candidate_id = bundle.candidates[0].candidate_id
        bundle.metadata["num_candidates"] = len(bundle.candidates)
        return bundle

    def parse_json_program(self, text_or_json: str) -> ProgramLike:
        payload = json.loads(text_or_json)
        if str(payload.get("bundle_type", "")).lower() == "program_bundle" or "candidates" in payload:
            return self.parse_json_bundle(text_or_json).selected_program()
        if str(payload.get("program_schema_mode", "")).lower() == "operatorized" or "steps" in payload:
            return self._operator_program_from_openai_payload(
                payload,
                source_text=text_or_json,
                scene_context=None,
            )
        target_name = canonicalize_label_name(str(payload.get("target", "others"))) or "others"
        target_label_ids = label_ids_from_names([target_name])
        attributes = [
            canonicalize_attribute_name(str(item))
            for item in self._as_list(payload.get("attributes"))
            if canonicalize_attribute_name(str(item)) is not None
        ]
        relations = []
        for relation_payload in self._as_list(payload.get("relations")):
            if not isinstance(relation_payload, dict):
                continue
            relation_type = canonicalize_relation_type(str(relation_payload.get("type", "near"))) or "near"
            reference_name = canonicalize_label_name(str(relation_payload.get("reference", "")))
            if reference_name is None:
                continue
            relations.append(
                RelationClause(
                    type=relation_type,
                    reference=reference_name,
                    reference_label_ids=label_ids_from_names([reference_name]),
                    distance_m=relation_payload.get("distance_m"),
                    margin_m=relation_payload.get("margin_m"),
                    evidence=list(RELATION_EVIDENCE.get(relation_type, [])),
                )
            )
        negatives = []
        for item in self._as_list(payload.get("negatives")):
            normalized = canonicalize_label_name(str(item))
            if normalized is not None:
                negatives.append(normalized)
        if self.config.enable_default_negatives:
            negatives = ensure_negative_priors(target_name, negatives)
        evidence = merge_evidence(attributes, relations)
        return HydrologicalProgram(
            target=target_name,
            target_label_ids=target_label_ids,
            attributes=unique_list(attributes),
            relations=relations,
            negatives=unique_list(negatives),
            negative_label_ids=label_ids_from_names(negatives),
            evidence=evidence,
            metadata={"compiler": "json"},
            source_text=text_or_json,
        )

    def parse_json_bundle(self, text_or_json: str) -> ProgramBundle:
        payload = json.loads(text_or_json)
        if str(payload.get("bundle_type", "")).lower() == "program_bundle" or "candidates" in payload:
            candidates = []
            for index, item in enumerate(payload.get("candidates", [])):
                if not isinstance(item, dict):
                    continue
                candidate_payload = dict(item)
                program_payload = candidate_payload.get("program", {})
                if isinstance(program_payload, dict):
                    program = self.parse_json_program(json.dumps(program_payload))
                    candidate_payload["program"] = program.to_dict()
                candidate_payload.setdefault("candidate_id", f"c{index}")
                candidates.append(ProgramCandidate.from_dict(candidate_payload))
            if not candidates:
                raise ValueError("Program bundle payload must contain at least one valid candidate.")
            return ProgramBundle(
                source_text=str(payload.get("source_text", "")),
                candidates=candidates,
                selected_candidate_id=str(payload.get("selected_candidate_id", candidates[0].candidate_id)),
                metadata=dict(payload.get("metadata", {})),
            )
        program = self.parse_json_program(text_or_json)
        return ProgramBundle(
            source_text=getattr(program, "source_text", ""),
            candidates=[ProgramCandidate(candidate_id="c0", program=program, proposal_score=1.0, proposal_source="single_program")],
            selected_candidate_id="c0",
            metadata={"wrapped_single_program": True},
        )

    def _sanitize_program(
        self,
        program: ProgramLike,
        scene_context: Optional[Dict[str, Any]] = None,
    ) -> ProgramLike:
        if not self.config.enable_program_repair:
            return program
        if not isinstance(program, OperatorizedSpatialProgram):
            return program
        steps: List[ProgramStep] = []
        repair_notes: List[str] = []
        current_input: Optional[str] = None
        step_index = 1
        existing_negative_labels = {step.label for step in program.steps if step.op == "exclude" and step.label is not None}

        def next_step_id() -> str:
            nonlocal step_index
            step_id = f"s{step_index}"
            step_index += 1
            return step_id

        for original in program.steps:
            step = ProgramStep.from_dict(original.to_dict())
            step.id = next_step_id()
            if step.op == "select":
                step.input = None
                select_attr = step.attribute
                if step.attribute is not None:
                    step.attribute = None
                    repair_notes.append(f"moved_select_attribute:{original.id}")
                if step.relation is not None:
                    step.relation = None
                    step.reference_label = None
                    step.reference_label_ids = []
                    step.distance_m = None
                    step.margin_m = None
                    repair_notes.append(f"cleared_select_relation:{original.id}")
                if step.label is None and program.target:
                    step.label = program.target
                    step.label_ids = list(program.target_label_ids)
                    repair_notes.append(f"filled_select_label:{original.id}")
                steps.append(step)
                current_input = step.id
                if select_attr is not None:
                    filter_step = ProgramStep(
                        id=next_step_id(),
                        op="filter",
                        input=current_input,
                        attribute=select_attr,
                        evidence=list(DEFAULT_EVIDENCE.get(select_attr, [])),
                    )
                    steps.append(filter_step)
                    current_input = filter_step.id
                continue
            if step.op in {"filter", "relate", "exclude"}:
                step.input = current_input if current_input is not None else step.input
                steps.append(step)
                current_input = step.id
                continue
            if step.op == "compose":
                if not step.inputs and current_input is not None:
                    step.inputs = [current_input]
                steps.append(step)
                current_input = step.id
                continue
            steps.append(step)
            current_input = step.id

        if program.attributes:
            has_filter = any(step.op == "filter" for step in steps)
            if not has_filter:
                for attribute in program.attributes:
                    filter_step = ProgramStep(
                        id=next_step_id(),
                        op="filter",
                        input=current_input,
                        attribute=attribute,
                        evidence=list(DEFAULT_EVIDENCE.get(attribute, [])),
                    )
                    steps.append(filter_step)
                    current_input = filter_step.id
                    repair_notes.append(f"added_missing_filter:{attribute}")
        if program.relations:
            has_relate = any(step.op == "relate" for step in steps)
            if not has_relate:
                for relation in program.relations:
                    relate_step = ProgramStep(
                        id=next_step_id(),
                        op="relate",
                        input=current_input,
                        relation=relation.type,
                        reference_label=relation.reference,
                        reference_label_ids=list(relation.reference_label_ids),
                        distance_m=relation.distance_m,
                        margin_m=relation.margin_m,
                        evidence=list(relation.evidence),
                    )
                    steps.append(relate_step)
                    current_input = relate_step.id
                    repair_notes.append(f"added_missing_relate:{relation.type}:{relation.reference}")
        if program.negatives:
            for negative_name in program.negatives:
                if negative_name in existing_negative_labels:
                    continue
                exclude_step = ProgramStep(
                    id=next_step_id(),
                    op="exclude",
                    input=current_input,
                    label=negative_name,
                    label_ids=label_ids_from_names([negative_name]),
                    evidence=["class_logits"],
                )
                steps.append(exclude_step)
                current_input = exclude_step.id
                repair_notes.append(f"added_missing_exclude:{negative_name}")

        sanitized = OperatorizedSpatialProgram(
            program_version=program.program_version,
            target=program.target,
            target_label_ids=list(program.target_label_ids),
            attributes=list(program.attributes),
            relations=[RelationClause.from_dict(item.to_dict()) for item in program.relations],
            negatives=list(program.negatives),
            negative_label_ids=list(program.negative_label_ids),
            steps=steps,
            output_step_id=current_input or program.output_step_id,
            evidence=list(program.evidence),
            metadata=dict(program.metadata),
            source_text=program.source_text,
        )
        metadata = dict(sanitized.metadata)
        metadata["sanitizer_applied"] = bool(repair_notes)
        metadata["sanitizer_report"] = repair_notes
        return sanitized.with_metadata(**metadata)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " " + " ".join(text.lower().replace("_", " ").split()) + " "

    def _infer_target_name(self, normalized_text: str) -> Optional[str]:
        relation_refs = {relation.reference for relation in self._infer_relations(normalized_text)}
        negatives = set(self._infer_negatives(normalized_text))
        mentions = self._find_label_mentions(normalized_text)
        for name in mentions:
            if name not in relation_refs and name not in negatives:
                return name
        return mentions[0] if mentions else None

    def _find_label_mentions(self, normalized_text: str) -> List[str]:
        mentions: List[str] = []
        offsets: Dict[str, int] = {}
        alias_keys = sorted(set(list(label_names_from_ids(range(15))) + list(self._alias_keys())), key=len, reverse=True)
        for alias in alias_keys:
            pattern = re.compile(rf"\b{re.escape(alias)}\b")
            match = pattern.search(normalized_text)
            if match is None:
                continue
            canonical = canonicalize_label_name(alias)
            if canonical is None:
                continue
            start = int(match.start())
            if canonical not in offsets or start < offsets[canonical]:
                offsets[canonical] = start
        for name, _ in sorted(offsets.items(), key=lambda item: item[1]):
            mentions.append(name)
        return mentions

    @staticmethod
    def _alias_keys() -> Sequence[str]:
        from .schema import LABEL_ALIASES

        return LABEL_ALIASES.keys()

    def _infer_attributes(self, normalized_text: str) -> List[str]:
        attributes: List[str] = []
        from .schema import ATTRIBUTE_ALIASES

        for alias in sorted(ATTRIBUTE_ALIASES.keys(), key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", normalized_text):
                canonical = canonicalize_attribute_name(alias)
                if canonical is not None and canonical not in attributes:
                    attributes.append(canonical)
        return attributes

    def _infer_relations(self, normalized_text: str) -> List[RelationClause]:
        relations: List[RelationClause] = []
        alias_pattern = "|".join(sorted({re.escape(alias) for alias in self._alias_keys()}, key=len, reverse=True))
        patterns = {
            "near": rf"(?:near|adjacent to)\s+(?P<label>{alias_pattern})",
            "along": rf"(?:along)\s+(?P<label>{alias_pattern})",
            "above": rf"(?:above|higher than)\s+(?P<label>{alias_pattern})",
            "below": rf"(?:below|lower than)\s+(?P<label>{alias_pattern})",
        }
        for relation_type, pattern in patterns.items():
            for match in re.finditer(pattern, normalized_text):
                reference = canonicalize_label_name(match.group("label"))
                if reference is None:
                    continue
                distance_m = None
                margin_m = None
                if relation_type in {"near", "adjacent", "along"}:
                    distance_m = self.config.relation_distance_overrides.get(
                        relation_type,
                        self.config.default_near_distance_m,
                    )
                else:
                    margin_m = self.config.default_above_margin_m
                relations.append(
                    RelationClause(
                        type=relation_type,
                        reference=reference,
                        reference_label_ids=label_ids_from_names([reference]),
                        distance_m=distance_m,
                        margin_m=margin_m,
                        evidence=list(RELATION_EVIDENCE.get(relation_type, [])),
                    )
                )
        unique: List[RelationClause] = []
        seen = set()
        for relation in relations:
            key = (relation.type, relation.reference)
            if key in seen:
                continue
            seen.add(key)
            unique.append(relation)
        return unique

    def _infer_negatives(self, normalized_text: str) -> List[str]:
        negatives: List[str] = []
        alias_pattern = "|".join(sorted({re.escape(alias) for alias in self._alias_keys()}, key=len, reverse=True))
        pattern = re.compile(rf"(?:not|instead of|rather than)\s+(?P<label>{alias_pattern})")
        for match in pattern.finditer(normalized_text):
            reference = canonicalize_label_name(match.group("label"))
            if reference is not None and reference not in negatives:
                negatives.append(reference)
        return negatives

    @staticmethod
    def _sample_target_label_ids(sample: Dict[str, Any]) -> List[int]:
        raw_ids = [int(label_id) for label_id in sample.get("target_label_ids", [])]
        return sorted(set(max(label_id - 1, 0) for label_id in raw_ids))

    def _sample_relations(self, sample: Dict[str, Any]) -> List[RelationClause]:
        relations: List[RelationClause] = []
        for payload in sample.get("spatial_relations", []):
            if not isinstance(payload, dict):
                continue
            relation_type = canonicalize_relation_type(str(payload.get("type", "")))
            reference_name = canonicalize_label_name(str(payload.get("reference_name", payload.get("reference", ""))))
            if relation_type is None or reference_name is None:
                continue
            relations.append(
                RelationClause(
                    type=relation_type,
                    reference=reference_name,
                    reference_label_ids=label_ids_from_names([reference_name]),
                    distance_m=payload.get("distance_threshold_m", payload.get("distance_m")),
                    margin_m=payload.get("z_margin_m", payload.get("margin_m")),
                    evidence=list(RELATION_EVIDENCE.get(relation_type, [])),
                )
            )
        return relations
