from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence


ACTION_TYPES = {"direct_answer", "tool_call", "workflow", "clarification", "abstain"}
INTENTS = {
    "class_presence", "class_segmentation", "attribute_judgement",
    "attribute_segmentation", "relation_judgement", "relation_segmentation",
    "full_scene_segmentation",
}
VERIFICATION_POLICIES = {"auto", "required", "skip"}
STEP_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,47}$")


@dataclass
class Container:
    kind: str
    path: tuple[str, ...]
    expect: str
    keys: set[str] = field(default_factory=set)
    pending_key: Optional[str] = None


@dataclass
class PrefixResult:
    valid: bool
    complete: bool
    mode: str
    path: tuple[str, ...]
    depth: int
    error: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_prefix": self.valid,
            "complete": self.complete,
            "mode": self.mode,
            "path": list(self.path),
            "depth": self.depth,
            "error": self.error,
        }


def is_non_progress_json_whitespace(
    state: PrefixResult,
    current_text: str,
    candidate_text: str,
) -> bool:
    """Return whether a candidate only adds ignorable JSON whitespace."""
    if state.mode != "normal" or not candidate_text.startswith(current_text):
        return False
    suffix = candidate_text[len(current_text) :]
    return bool(suffix) and suffix.isspace()


class AgentRequestPrefixParser:
    """Incremental JSON lexer/parser with AgentRequest field and enum constraints."""

    ROOT_KEYS = {"schema_version", "request_id", "intent", "action", "expected_output"}
    ROOT_REQUIRED_KEYS = {"schema_version", "request_id", "intent", "action"}
    STEP_REQUIRED_KEYS = {"step_id", "tool", "arguments"}
    ACTION_KEYS = {
        "type", "answer", "tool", "arguments", "verification", "steps",
        "question", "missing_fields", "reason", "error_code", "recoverable",
    }
    STEP_KEYS = {"step_id", "tool", "arguments", "depends_on", "verification"}
    EXPECTED_KEYS = {"type", "coordinate_space"}

    def __init__(
        self,
        tool_names: Iterable[str],
        argument_properties: Mapping[str, Mapping[str, Any]],
        result_types: Iterable[str],
        coordinate_spaces: Iterable[str],
        complete_validator: Optional[Callable[[Mapping[str, Any]], bool]] = None,
    ) -> None:
        self.tool_names = set(tool_names)
        self.argument_properties = {str(k): dict(v) for k, v in argument_properties.items()}
        self.result_types = set(result_types) | {"text"}
        self.coordinate_spaces = set(coordinate_spaces) | {"none"}
        self.complete_validator = complete_validator
        self.stack: list[Container] = []
        self.root_expect = "value"
        self.mode = "normal"
        self.string_role: Optional[str] = None
        self.string_buffer = ""
        self.scalar_path: tuple[str, ...] = ()
        self.literal_target = ""
        self.literal_buffer = ""
        self.number_buffer = ""
        self.unicode_buffer = ""
        self.error: Optional[str] = None
        self.completed_value: Optional[Any] = None
        self.text = ""

    def clone(self) -> "AgentRequestPrefixParser":
        cloned = copy.copy(self)
        cloned.stack = [
            Container(item.kind, item.path, item.expect, set(item.keys), item.pending_key)
            for item in self.stack
        ]
        cloned.completed_value = self.completed_value
        return cloned

    def _fail(self, message: str) -> bool:
        self.error = message
        return False

    def _expect(self) -> str:
        return self.stack[-1].expect if self.stack else self.root_expect

    def _value_path(self) -> tuple[str, ...]:
        if not self.stack:
            return ()
        parent = self.stack[-1]
        if parent.kind == "object":
            if parent.pending_key is None:
                return parent.path + ("?",)
            return parent.path + (parent.pending_key,)
        return parent.path + ("[]",)

    def _allowed_keys(self, path: tuple[str, ...]) -> Optional[set[str]]:
        if path == ():
            return self.ROOT_KEYS
        if path == ("action",):
            return self.ACTION_KEYS
        if path == ("expected_output",):
            return self.EXPECTED_KEYS
        if path == ("action", "steps", "[]"):
            return self.STEP_KEYS
        if "arguments" in path:
            return set(self.argument_properties)
        return None

    def _required_keys(self, path: tuple[str, ...]) -> set[str]:
        if path == ():
            return self.ROOT_REQUIRED_KEYS
        if path == ("action", "steps", "[]"):
            return self.STEP_REQUIRED_KEYS
        return set()

    def _container_can_close(self, container: Container) -> bool:
        if container.kind != "object":
            return True
        missing = self._required_keys(container.path) - container.keys
        if missing:
            return self._fail(
                f"object at {container.path} is missing required fields {sorted(missing)}"
            )
        return True

    def _step_id_prefix_valid(self, value: str, complete: bool = False) -> bool:
        if not value or len(value) > 48:
            return False
        if not value[0].isalpha() or not value[0].isascii():
            return False
        if any(not (char.isascii() and (char.isalnum() or char in "_-")) for char in value[1:]):
            return False
        return not complete or STEP_ID_PATTERN.fullmatch(value) is not None

    def _enum(self, path: tuple[str, ...]) -> Optional[set[str]]:
        if path == ("schema_version",):
            return {"1.0"}
        if path == ("intent",):
            return INTENTS
        if path == ("action", "type"):
            return ACTION_TYPES
        if path in {("action", "tool"), ("action", "steps", "[]", "tool")}:
            return self.tool_names
        if path in {("action", "verification"), ("action", "steps", "[]", "verification")}:
            return VERIFICATION_POLICIES
        if path == ("expected_output", "type"):
            return self.result_types
        if path == ("expected_output", "coordinate_space"):
            return self.coordinate_spaces
        if "arguments" in path and path:
            schema = self.argument_properties.get(path[-1], {})
            enum = schema.get("enum")
            if isinstance(enum, list) and all(isinstance(v, str) for v in enum):
                return set(enum)
        return None

    def _expected_types(self, path: tuple[str, ...]) -> Optional[set[str]]:
        fixed = {
            ("schema_version",): {"string"}, ("request_id",): {"string"},
            ("intent",): {"string"}, ("action",): {"object"},
            ("expected_output",): {"object"}, ("action", "type"): {"string"},
            ("action", "answer"): {"string"}, ("action", "tool"): {"string"},
            ("action", "arguments"): {"object"}, ("action", "verification"): {"string"},
            ("action", "steps"): {"array"}, ("action", "question"): {"string"},
            ("action", "missing_fields"): {"array"}, ("action", "reason"): {"string"},
            ("action", "error_code"): {"string"}, ("action", "recoverable"): {"boolean"},
            ("expected_output", "type"): {"string"},
            ("expected_output", "coordinate_space"): {"string"},
            ("action", "steps", "[]"): {"object"},
            ("action", "steps", "[]", "step_id"): {"string"},
            ("action", "steps", "[]", "tool"): {"string"},
            ("action", "steps", "[]", "arguments"): {"object"},
            ("action", "steps", "[]", "depends_on"): {"array"},
            ("action", "steps", "[]", "verification"): {"string"},
        }
        if path in fixed:
            return fixed[path]
        if "arguments" in path and path:
            schema = self.argument_properties.get(path[-1])
            if schema and isinstance(schema.get("type"), str):
                return {str(schema["type"])}
        if path and path[-1] == "[]":
            parent = path[:-1]
            if parent in {("action", "missing_fields"), ("action", "steps", "[]", "depends_on")}:
                return {"string"}
            if "arguments" in parent:
                schema = self.argument_properties.get(parent[-1], {})
                items = schema.get("items", {})
                if isinstance(items, Mapping) and isinstance(items.get("type"), str):
                    return {str(items["type"])}
        return None

    def _check_type_start(self, path: tuple[str, ...], value_type: str) -> bool:
        expected = self._expected_types(path)
        return expected is None or value_type in expected

    def _key_prefix_valid(self, value: str) -> bool:
        allowed = self._allowed_keys(self.stack[-1].path) if self.stack else None
        if allowed is None:
            return True
        available = allowed - self.stack[-1].keys
        return any(key.startswith(value) for key in available)

    def _value_string_prefix_valid(self, value: str) -> bool:
        enum = self._enum(self.scalar_path)
        return enum is None or any(item.startswith(value) for item in enum)

    def _value_complete(self) -> bool:
        if self.stack:
            parent = self.stack[-1]
            parent.expect = "comma_or_end"
            if parent.kind == "object":
                parent.pending_key = None
        else:
            self.root_expect = "done"
            try:
                value, _ = json.JSONDecoder().raw_decode(self.text.lstrip())
            except json.JSONDecodeError:
                return self._fail("complete JSON could not be decoded")
            if not isinstance(value, Mapping):
                return self._fail("top-level value must be an object")
            if self.complete_validator is not None and not self.complete_validator(value):
                return self._fail("complete object violates AgentRequest schema")
            self.completed_value = value
        return True

    def _start_value(self, char: str) -> tuple[bool, bool]:
        path = self._value_path()
        if char == "{":
            if not self._check_type_start(path, "object"):
                return self._fail(f"object not allowed at {path}"), False
            self.stack.append(Container("object", path, "key_or_end"))
            return True, False
        if char == "[":
            if not self._check_type_start(path, "array"):
                return self._fail(f"array not allowed at {path}"), False
            self.stack.append(Container("array", path, "value_or_end"))
            return True, False
        if char == '"':
            if not self._check_type_start(path, "string"):
                return self._fail(f"string not allowed at {path}"), False
            self.mode, self.string_role, self.string_buffer, self.scalar_path = "string", "value", "", path
            return True, False
        if char in "-0123456789":
            if not (self._check_type_start(path, "number") or self._check_type_start(path, "integer")):
                return self._fail(f"number not allowed at {path}"), False
            self.mode, self.number_buffer, self.scalar_path = "number", char, path
            return True, False
        targets = {"t": ("true", "boolean"), "f": ("false", "boolean"), "n": ("null", "null")}
        if char in targets:
            target, value_type = targets[char]
            if not self._check_type_start(path, value_type):
                return self._fail(f"{value_type} not allowed at {path}"), False
            self.mode, self.literal_target, self.literal_buffer, self.scalar_path = "literal", target, char, path
            return True, False
        return self._fail(f"invalid value start {char!r} at {path}"), False

    def feed(self, fragment: str) -> bool:
        if self.error is not None:
            return False
        self.text += fragment
        index = len(self.text) - len(fragment)
        while index < len(self.text):
            char = self.text[index]
            if self.mode == "string":
                if ord(char) < 0x20:
                    return self._fail("unescaped control character in string")
                if char == "\\":
                    if self.string_role == "key":
                        return self._fail("escaped characters are not allowed in schema field names")
                    if self.string_role == "value" and self._enum(self.scalar_path) is not None:
                        return self._fail("escaped characters are not allowed in schema enum values")
                    self.mode = "escape"
                elif char == '"':
                    if self.string_role == "key":
                        container = self.stack[-1]
                        allowed = self._allowed_keys(container.path)
                        if allowed is not None and self.string_buffer not in allowed:
                            return self._fail(f"field {self.string_buffer!r} is not allowed at {container.path}")
                        if self.string_buffer in container.keys:
                            return self._fail(f"duplicate field {self.string_buffer!r}")
                        container.keys.add(self.string_buffer)
                        container.pending_key = self.string_buffer
                        container.expect = "colon"
                    else:
                        enum = self._enum(self.scalar_path)
                        if enum is not None and self.string_buffer not in enum:
                            return self._fail(f"value {self.string_buffer!r} is not an allowed enum")
                        if self.scalar_path == ("action", "steps", "[]", "step_id") and not self._step_id_prefix_valid(
                            self.string_buffer, complete=True
                        ):
                            return self._fail("workflow step_id has an invalid identifier format")
                        if not self._value_complete():
                            return False
                    self.mode = "normal"
                else:
                    self.string_buffer += char
                    if self.string_role == "key" and not self._key_prefix_valid(self.string_buffer):
                        return self._fail(f"no allowed field starts with {self.string_buffer!r}")
                    if self.string_role == "value" and not self._value_string_prefix_valid(self.string_buffer):
                        return self._fail(f"no allowed enum starts with {self.string_buffer!r}")
                    if self.string_role == "value" and self.scalar_path == (
                        "action", "steps", "[]", "step_id"
                    ) and not self._step_id_prefix_valid(self.string_buffer):
                        return self._fail("workflow step_id has an invalid identifier prefix")
                index += 1
                continue
            if self.mode == "escape":
                if char in '"\\/bfnrt':
                    self.string_buffer += {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}.get(char, char)
                    if self.string_role == "key" and not self._key_prefix_valid(self.string_buffer):
                        return self._fail(f"no allowed field starts with {self.string_buffer!r}")
                    if self.string_role == "value" and not self._value_string_prefix_valid(self.string_buffer):
                        return self._fail(f"no allowed enum starts with {self.string_buffer!r}")
                    self.mode = "string"
                elif char == "u":
                    self.mode, self.unicode_buffer = "unicode", ""
                else:
                    return self._fail("invalid JSON escape")
                index += 1
                continue
            if self.mode == "unicode":
                if char not in "0123456789abcdefABCDEF":
                    return self._fail("invalid unicode escape")
                self.unicode_buffer += char
                if len(self.unicode_buffer) == 4:
                    self.string_buffer += chr(int(self.unicode_buffer, 16))
                    if self.string_role == "key" and not self._key_prefix_valid(self.string_buffer):
                        return self._fail(f"no allowed field starts with {self.string_buffer!r}")
                    if self.string_role == "value" and not self._value_string_prefix_valid(self.string_buffer):
                        return self._fail(f"no allowed enum starts with {self.string_buffer!r}")
                    self.mode = "string"
                index += 1
                continue
            if self.mode == "literal":
                if len(self.literal_buffer) < len(self.literal_target):
                    expected = self.literal_target[len(self.literal_buffer)]
                    if char != expected:
                        return self._fail(f"invalid literal; expected {expected!r}")
                    self.literal_buffer += char
                    index += 1
                    continue
                self.mode = "normal"
                if not self._value_complete():
                    return False
                continue
            if self.mode == "number":
                if char in "0123456789+-.eE":
                    self.number_buffer += char
                    index += 1
                    continue
                try:
                    json.loads(self.number_buffer)
                except json.JSONDecodeError:
                    return self._fail("invalid JSON number")
                self.mode = "normal"
                if not self._value_complete():
                    return False
                continue

            expect = self._expect()
            if expect == "done":
                if not char.isspace():
                    return self._fail("content after complete top-level object")
                index += 1
            elif char.isspace():
                index += 1
            elif expect in {"value", "value_or_end"}:
                if expect == "value_or_end" and char == "]":
                    self.stack.pop()
                    if not self._value_complete():
                        return False
                    index += 1
                else:
                    ok, consumed_again = self._start_value(char)
                    if not ok:
                        return False
                    index += 0 if consumed_again else 1
            elif expect == "key_or_end":
                if char == "}":
                    if not self._container_can_close(self.stack[-1]):
                        return False
                    self.stack.pop()
                    if not self._value_complete():
                        return False
                    index += 1
                elif char == '"':
                    self.mode, self.string_role, self.string_buffer = "string", "key", ""
                    index += 1
                else:
                    return self._fail("object expects a quoted field name or closing brace")
            elif expect == "colon":
                if char != ":":
                    return self._fail("object field expects colon")
                self.stack[-1].expect = "value"
                index += 1
            elif expect == "comma_or_end":
                container = self.stack[-1]
                closer = "}" if container.kind == "object" else "]"
                if char == closer:
                    if not self._container_can_close(container):
                        return False
                    self.stack.pop()
                    if not self._value_complete():
                        return False
                    index += 1
                elif char == ",":
                    if container.kind == "object":
                        allowed = self._allowed_keys(container.path)
                        if allowed is not None and not (allowed - container.keys):
                            return self._fail(f"object at {container.path} has no unused fields")
                    container.expect = "key_or_end" if container.kind == "object" else "value"
                    index += 1
                else:
                    return self._fail(f"container expects comma or {closer}")
            else:
                return self._fail(f"unknown parser expectation {expect}")
        return True

    def result(self) -> PrefixResult:
        path = self.scalar_path if self.mode != "normal" else (self.stack[-1].path if self.stack else ())
        return PrefixResult(
            valid=self.error is None,
            complete=self.error is None and self.root_expect == "done" and self.mode == "normal",
            mode=self.mode,
            path=path,
            depth=len(self.stack),
            error=self.error,
        )


def union_argument_properties(tool_schemas: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for schema in tool_schemas:
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            continue
        for name, value in properties.items():
            if name not in result and isinstance(value, Mapping):
                result[str(name)] = dict(value)
    return result
