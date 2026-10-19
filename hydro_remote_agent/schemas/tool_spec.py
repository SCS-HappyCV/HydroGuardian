from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml


TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
SUPPORTED_SCHEMA_TYPES = {
    "array",
    "boolean",
    "integer",
    "null",
    "number",
    "object",
    "string",
}
SUPPORTED_INPUT_MODALITIES = {
    "before_image",
    "change_prediction",
    "image",
    "point_cloud",
    "query_text",
    "reference_result",
    "segmentation_prediction",
}
SUPPORTED_RESULT_TYPES = {
    "change_mask",
    "geometry_report",
    "image_mask",
    "point_labels",
    "point_mask",
    "quality_report",
}


class ToolSpecError(ValueError):
    """Raised when a tool registry violates its contract."""


class ToolArgumentError(ValueError):
    """Raised when a tool call does not satisfy its argument schema."""


def _as_string_tuple(value: Any, field_name: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ToolSpecError(f"{field_name} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _require_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ToolSpecError(f"{field_name} must be an object")
    return dict(value)


def _validate_json_schema(schema: Mapping[str, Any], path: str) -> None:
    schema_type = schema.get("type")
    if schema_type not in SUPPORTED_SCHEMA_TYPES:
        raise ToolSpecError(f"{path}.type must be one of {sorted(SUPPORTED_SCHEMA_TYPES)}")

    if schema_type == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ToolSpecError(f"{path}.properties must be an object")
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise ToolSpecError(f"{path}.required must be a list of strings")
        missing = sorted(set(required) - set(properties))
        if missing:
            raise ToolSpecError(f"{path}.required references undefined properties: {missing}")
        for name, child in properties.items():
            if not isinstance(child, dict):
                raise ToolSpecError(f"{path}.properties.{name} must be an object")
            _validate_json_schema(child, f"{path}.properties.{name}")

    if schema_type == "array":
        items = schema.get("items")
        if not isinstance(items, dict):
            raise ToolSpecError(f"{path}.items must be an object")
        _validate_json_schema(items, f"{path}.items")

    enum = schema.get("enum")
    if enum is not None and (not isinstance(enum, list) or not enum):
        raise ToolSpecError(f"{path}.enum must be a non-empty list")


def _matches_schema_type(value: Any, schema_type: str) -> bool:
    if schema_type == "null":
        return value is None
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "object":
        return isinstance(value, dict)
    return False


def _validate_value(value: Any, schema: Mapping[str, Any], path: str) -> None:
    schema_type = str(schema["type"])
    if not _matches_schema_type(value, schema_type):
        raise ToolArgumentError(f"{path} must have type {schema_type}")

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        raise ToolArgumentError(f"{path} must be one of {enum}")

    if schema_type == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = [name for name in required if name not in value]
        if missing:
            raise ToolArgumentError(f"{path} is missing required fields: {missing}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ToolArgumentError(f"{path} has unknown fields: {unknown}")
        for name, child_value in value.items():
            child_schema = properties.get(name)
            if child_schema is not None:
                _validate_value(child_value, child_schema, f"{path}.{name}")
        return

    if schema_type == "array":
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise ToolArgumentError(f"{path} must contain at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ToolArgumentError(f"{path} must contain at most {schema['maxItems']} items")
        if schema.get("uniqueItems") is True:
            normalized = [repr(item) for item in value]
            if len(set(normalized)) != len(normalized):
                raise ToolArgumentError(f"{path} must contain unique items")
        for index, item in enumerate(value):
            _validate_value(item, schema["items"], f"{path}[{index}]")
        return

    if schema_type in {"integer", "number"}:
        numeric_value = float(value)
        if "minimum" in schema and numeric_value < float(schema["minimum"]):
            raise ToolArgumentError(f"{path} must be >= {schema['minimum']}")
        if "maximum" in schema and numeric_value > float(schema["maximum"]):
            raise ToolArgumentError(f"{path} must be <= {schema['maximum']}")
        if "exclusiveMinimum" in schema and numeric_value <= float(schema["exclusiveMinimum"]):
            raise ToolArgumentError(f"{path} must be > {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and numeric_value >= float(schema["exclusiveMaximum"]):
            raise ToolArgumentError(f"{path} must be < {schema['exclusiveMaximum']}")
        return

    if schema_type == "string":
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ToolArgumentError(f"{path} must contain at least {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ToolArgumentError(f"{path} must contain at most {schema['maxLength']} characters")


@dataclass(frozen=True)
class ResourceSpec:
    device: str = "cpu"
    min_gpu_memory_gb: float = 0.0
    timeout_seconds: float = 60.0
    supports_batching: bool = False

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResourceSpec":
        device = str(payload.get("device", "cpu")).strip().lower()
        if device not in {"cpu", "cuda", "either"}:
            raise ToolSpecError("resources.device must be cpu, cuda, or either")
        min_gpu_memory_gb = float(payload.get("min_gpu_memory_gb", 0.0))
        timeout_seconds = float(payload.get("timeout_seconds", 60.0))
        if min_gpu_memory_gb < 0:
            raise ToolSpecError("resources.min_gpu_memory_gb cannot be negative")
        if timeout_seconds <= 0:
            raise ToolSpecError("resources.timeout_seconds must be positive")
        return cls(
            device=device,
            min_gpu_memory_gb=min_gpu_memory_gb,
            timeout_seconds=timeout_seconds,
            supports_batching=bool(payload.get("supports_batching", False)),
        )


@dataclass(frozen=True)
class OutputSpec:
    result_types: Tuple[str, ...]
    coordinate_space: str
    artifacts: Tuple[str, ...] = ()
    includes_confidence: bool = True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], tool_name: str) -> "OutputSpec":
        result_types = _as_string_tuple(payload.get("result_types"), f"{tool_name}.output.result_types")
        if not result_types:
            raise ToolSpecError(f"{tool_name}.output.result_types cannot be empty")
        unsupported = sorted(set(result_types) - SUPPORTED_RESULT_TYPES)
        if unsupported:
            raise ToolSpecError(f"{tool_name}.output has unsupported result types: {unsupported}")
        coordinate_space = str(payload.get("coordinate_space", "none")).strip()
        if not coordinate_space:
            raise ToolSpecError(f"{tool_name}.output.coordinate_space cannot be empty")
        return cls(
            result_types=result_types,
            coordinate_space=coordinate_space,
            artifacts=_as_string_tuple(payload.get("artifacts", []), f"{tool_name}.output.artifacts"),
            includes_confidence=bool(payload.get("includes_confidence", True)),
        )


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    capabilities: Tuple[str, ...]
    required_modalities: Tuple[str, ...]
    optional_modalities: Tuple[str, ...]
    arguments_schema: Dict[str, Any]
    output: OutputSpec
    resources: ResourceSpec
    deterministic: bool = False
    verifier: Optional[str] = None
    error_codes: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ToolSpec":
        name = str(payload.get("name", "")).strip()
        if not TOOL_NAME_PATTERN.fullmatch(name):
            raise ToolSpecError(f"Invalid tool name {name!r}; use lowercase snake_case")
        version = str(payload.get("version", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not version or not description:
            raise ToolSpecError(f"{name} requires non-empty version and description")

        capabilities = _as_string_tuple(payload.get("capabilities"), f"{name}.capabilities")
        if not capabilities:
            raise ToolSpecError(f"{name}.capabilities cannot be empty")

        inputs = _require_mapping(payload.get("inputs"), f"{name}.inputs")
        required_modalities = _as_string_tuple(inputs.get("required_modalities"), f"{name}.inputs.required_modalities")
        optional_modalities = _as_string_tuple(
            inputs.get("optional_modalities", []),
            f"{name}.inputs.optional_modalities",
        )
        unsupported_modalities = sorted(
            (set(required_modalities) | set(optional_modalities)) - SUPPORTED_INPUT_MODALITIES
        )
        if unsupported_modalities:
            raise ToolSpecError(f"{name} has unsupported input modalities: {unsupported_modalities}")
        overlap = sorted(set(required_modalities) & set(optional_modalities))
        if overlap:
            raise ToolSpecError(f"{name} modalities cannot be both required and optional: {overlap}")

        arguments_schema = _require_mapping(payload.get("arguments_schema"), f"{name}.arguments_schema")
        _validate_json_schema(arguments_schema, f"{name}.arguments_schema")
        if arguments_schema.get("type") != "object":
            raise ToolSpecError(f"{name}.arguments_schema must have type object")

        output = OutputSpec.from_dict(_require_mapping(payload.get("output"), f"{name}.output"), name)
        resources = ResourceSpec.from_dict(
            _require_mapping(payload.get("resources", {}), f"{name}.resources")
        )
        verifier_value = payload.get("verifier")
        verifier = str(verifier_value).strip() if verifier_value is not None else None
        if verifier == "":
            verifier = None

        return cls(
            name=name,
            version=version,
            description=description,
            capabilities=capabilities,
            required_modalities=required_modalities,
            optional_modalities=optional_modalities,
            arguments_schema=arguments_schema,
            output=output,
            resources=resources,
            deterministic=bool(payload.get("deterministic", False)),
            verifier=verifier,
            error_codes=_as_string_tuple(payload.get("error_codes", []), f"{name}.error_codes"),
        )

    def to_openai_tool(self) -> Dict[str, Any]:
        """Return the function-tool shape accepted by OpenAI-compatible clients."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.arguments_schema,
            },
        }

    def validate_arguments(self, arguments: Mapping[str, Any]) -> None:
        if not isinstance(arguments, Mapping):
            raise ToolArgumentError(f"Arguments for {self.name} must be an object")
        _validate_value(dict(arguments), self.arguments_schema, f"{self.name}.arguments")


@dataclass(frozen=True)
class ToolRegistry:
    schema_version: str
    tools: Tuple[ToolSpec, ...]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ToolRegistry":
        schema_version = str(payload.get("schema_version", "")).strip()
        if not schema_version:
            raise ToolSpecError("tool registry requires schema_version")
        raw_tools = payload.get("tools")
        if not isinstance(raw_tools, list) or not raw_tools:
            raise ToolSpecError("tool registry requires a non-empty tools list")
        tools = tuple(ToolSpec.from_dict(_require_mapping(item, "tools[]")) for item in raw_tools)
        names = [tool.name for tool in tools]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ToolSpecError(f"Duplicate tool names: {duplicates}")
        known_names = set(names)
        for tool in tools:
            if tool.verifier is not None and tool.verifier not in known_names:
                raise ToolSpecError(f"{tool.name}.verifier references unknown tool {tool.verifier!r}")
            if tool.verifier == tool.name:
                raise ToolSpecError(f"{tool.name} cannot verify itself")
        return cls(schema_version=schema_version, tools=tools)

    def get(self, name: str) -> ToolSpec:
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise KeyError(f"Unknown tool {name!r}")

    def names(self) -> Tuple[str, ...]:
        return tuple(tool.name for tool in self.tools)

    def openai_tools(self) -> List[Dict[str, Any]]:
        return [tool.to_openai_tool() for tool in self.tools]


def load_tool_registry(path: str | Path) -> ToolRegistry:
    registry_path = Path(path)
    with registry_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ToolSpecError(f"Tool registry {registry_path} must contain an object")
    return ToolRegistry.from_dict(payload)
