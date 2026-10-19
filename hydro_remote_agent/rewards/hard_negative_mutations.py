"""Deterministic single-concept mutations for AgentRequest reward stress tests."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Mutation:
    family: str
    name: str
    candidate: dict[str, Any] | str
    expected_changed_components: tuple[str, ...]
    expected_stable_components: tuple[str, ...]
    valid_expected: bool
    equivalence: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "name": self.name,
            "candidate": self.candidate,
            "expected_changed_components": list(self.expected_changed_components),
            "expected_stable_components": list(self.expected_stable_components),
            "valid_expected": self.valid_expected,
            "equivalence": self.equivalence,
            "note": self.note,
        }


COMMON_STABLE = ("schema", "action", "intent", "expected_output")


def _deepcopy(value: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(dict(value))


def _change_scalar(value: Any, key: str) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        if "class_id" in key:
            return value % 15 + 1
        return value + 1
    if isinstance(value, float):
        return value + 0.5
    if isinstance(value, list) and value:
        changed = list(value)
        changed[0] = _change_scalar(changed[0], key)
        if changed[0] in changed[1:]:
            changed[0] = 15 if changed[0] != 15 else 14
        return changed
    if isinstance(value, str):
        if value.startswith("${"):
            return value
        return value + ".mutated"
    return value


def _mutate_one_argument(arguments: dict[str, Any]) -> tuple[str, Any]:
    priority = [
        "target_class_ids", "target_class_id", "reference_class_id", "operation",
        "return_probabilities", "distance_threshold_m", "z_margin_m", "query",
        "image_path", "point_cloud_path",
    ]
    key = next((name for name in priority if name in arguments), sorted(arguments)[0])
    old = arguments[key]
    if key == "operation":
        new = "above" if old == "near" else "near"
    else:
        new = _change_scalar(old, key)
    arguments[key] = new
    return key, old


def _drop_optional_slot(arguments: dict[str, Any]) -> str | None:
    for key in ("return_probabilities", "y_flip", "distance_threshold_m", "z_margin_m", "reference_class_ids", "relation"):
        if key in arguments:
            del arguments[key]
            return key
    return None


def _replacement_call(arguments: Mapping[str, Any], current_tool: str) -> tuple[str, dict[str, Any]]:
    point_cloud = arguments.get("point_cloud_path", "/tmp/missing_points.xyz")
    image = arguments.get("image_path", "/tmp/missing_image.png")
    target_ids = arguments.get("target_class_ids", [1])
    if current_tool != "point_semantic_segmentation":
        return "point_semantic_segmentation", {
            "point_cloud_path": point_cloud,
            "return_probabilities": bool(arguments.get("return_probabilities", True)),
            "target_class_ids": target_ids,
        }
    return "multimodal_semantic_segmentation", {
        "image_path": image,
        "point_cloud_path": point_cloud,
        "return_probabilities": bool(arguments.get("return_probabilities", True)),
        "target_class_ids": target_ids,
    }


def _verification_flip(value: str) -> str:
    return {"required": "skip", "skip": "required", "auto": "required"}.get(value, "required")


def _reverse_dicts(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _reverse_dicts(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reverse_dicts(item) for item in value]
    return value


def _json_order_control(gold: Mapping[str, Any]) -> str:
    return json.dumps(_reverse_dicts(gold), ensure_ascii=False, separators=(",", ":"))


def _set_order_control(gold: Mapping[str, Any]) -> dict[str, Any] | None:
    candidate = _deepcopy(gold)
    action = candidate["action"]
    argument_blocks = [action.get("arguments", {})] if action["type"] == "tool_call" else [step.get("arguments", {}) for step in action["steps"]]
    for arguments in argument_blocks:
        for key in ("target_class_ids", "reference_class_ids"):
            if isinstance(arguments.get(key), list) and len(arguments[key]) > 1:
                arguments[key] = list(reversed(arguments[key]))
                return candidate
    return None


def _rename_workflow_steps(gold: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _deepcopy(gold)
    steps = candidate["action"]["steps"]
    rename = {step["step_id"]: f"node_{index}" for index, step in enumerate(steps, start=1)}
    for step in steps:
        old = step["step_id"]
        step["step_id"] = rename[old]
        step["depends_on"] = [rename.get(item, item) for item in step.get("depends_on", [])]
        raw = json.dumps(step.get("arguments", {}), ensure_ascii=False)
        for source, target in rename.items():
            raw = raw.replace(f"${{{source}.artifacts.", f"${{{target}.artifacts.")
        step["arguments"] = json.loads(raw)
    return candidate


def generate_mutations(gold: Mapping[str, Any]) -> list[Mutation]:
    action_type = str(gold["action"]["type"])
    mutations: list[Mutation] = [
        Mutation("equivalence", "json_key_order", _json_order_control(gold), (), (), True, True),
    ]
    set_order = _set_order_control(gold)
    if set_order is not None:
        mutations.append(Mutation("equivalence", "set_order", set_order, (), (), True, True))

    invalid = _deepcopy(gold)
    del invalid["action"]["type"]
    mutations.append(Mutation("invalid_schema", "missing_action_type", invalid, ("schema",), (), False))

    if action_type == "tool_call":
        action = gold["action"]
        tool = _deepcopy(gold)
        new_tool, new_arguments = _replacement_call(action["arguments"], action["tool"])
        tool["action"]["tool"] = new_tool
        tool["action"]["arguments"] = new_arguments
        mutations.append(Mutation("tool_replacement", "legal_alternate_tool", tool, ("tool_set", "argument_keys", "argument_values"), COMMON_STABLE, True))

        value = _deepcopy(gold)
        changed_key, _ = _mutate_one_argument(value["action"]["arguments"])
        mutations.append(Mutation("argument_value", f"change_{changed_key}", value, ("argument_values",), COMMON_STABLE + ("tool_set", "argument_keys"), True))

        slot = _deepcopy(gold)
        dropped = _drop_optional_slot(slot["action"]["arguments"])
        if dropped:
            mutations.append(Mutation("argument_slot", f"drop_{dropped}", slot, ("argument_keys", "argument_values"), COMMON_STABLE + ("tool_set",), True))

        verification = _deepcopy(gold)
        verification["action"]["verification"] = _verification_flip(str(verification["action"].get("verification", "auto")))
        mutations.append(Mutation("verification_stop", "flip_verification", verification, ("verification",), COMMON_STABLE + ("tool_set", "argument_keys", "argument_values"), True))
        return mutations

    steps = gold["action"]["steps"]
    renamed = _rename_workflow_steps(gold)
    mutations.append(Mutation(
        "equivalence", "workflow_step_id_alpha_rename", renamed, (), (), True, True,
        "Graph-isomorphic alpha-renaming must preserve semantic reward.",
    ))
    tool = _deepcopy(gold)
    first = tool["action"]["steps"][0]
    new_tool, new_arguments = _replacement_call(first["arguments"], first["tool"])
    first["tool"] = new_tool
    first["arguments"] = new_arguments
    mutations.append(Mutation("tool_replacement", "legal_first_node_tool", tool, ("tool_set", "workflow_nodes", "argument_keys", "argument_values"), COMMON_STABLE + ("workflow_edges", "artifact_references"), True))

    value = _deepcopy(gold)
    changed_key, _ = _mutate_one_argument(value["action"]["steps"][-1]["arguments"])
    mutations.append(Mutation("argument_value", f"change_terminal_{changed_key}", value, ("argument_values",), COMMON_STABLE + ("tool_set", "argument_keys", "workflow_nodes", "workflow_edges", "artifact_references"), True))

    slot = _deepcopy(gold)
    dropped = _drop_optional_slot(slot["action"]["steps"][-1]["arguments"])
    if not dropped:
        dropped = _drop_optional_slot(slot["action"]["steps"][0]["arguments"])
    if dropped:
        mutations.append(Mutation("argument_slot", f"drop_{dropped}", slot, ("argument_keys", "argument_values"), COMMON_STABLE + ("tool_set", "workflow_nodes", "workflow_edges", "artifact_references"), True))

    node = _deepcopy(gold)
    node["action"]["steps"][0]["verification"] = _verification_flip(str(node["action"]["steps"][0].get("verification", "auto")))
    mutations.append(Mutation("workflow_node", "node_policy_change", node, ("verification",), COMMON_STABLE + ("tool_set", "argument_keys", "argument_values", "workflow_nodes", "workflow_edges", "artifact_references"), True))

    dag = _deepcopy(gold)
    terminal = dag["action"]["steps"][-1]
    for key, item in list(terminal["arguments"].items()):
        if isinstance(item, str) and item.startswith("${"):
            terminal["arguments"][key] = "/tmp/wrong_upstream_artifact.bin"
            terminal["depends_on"] = []
            mutations.append(Mutation(
                "dag_link", "detach_dependency_and_materialize_wrong_artifact", dag,
                ("workflow_edges", "artifact_references", "argument_values"),
                COMMON_STABLE + ("tool_set", "argument_keys", "workflow_nodes"), True,
                False,
                "Edge and artifact reference are schema-coupled; this is the smallest valid DAG-link mutation.",
            ))
            break

    artifact = _deepcopy(gold)
    terminal = artifact["action"]["steps"][-1]
    for key, item in list(terminal["arguments"].items()):
        if isinstance(item, str) and item.startswith("${"):
            producer = terminal["depends_on"][0]
            terminal["arguments"][key] = f"${{{producer}.artifacts.class_probabilities}}"
            mutations.append(Mutation("artifact_reference", "alternate_valid_artifact", artifact, ("artifact_references", "argument_values"), COMMON_STABLE + ("tool_set", "argument_keys", "workflow_nodes", "workflow_edges"), True))
            break

    verification = _deepcopy(gold)
    verification["action"]["steps"][-1]["verification"] = _verification_flip(str(verification["action"]["steps"][-1].get("verification", "auto")))
    mutations.append(Mutation("verification_stop", "flip_terminal_verification", verification, ("verification",), COMMON_STABLE + ("tool_set", "argument_keys", "argument_values", "workflow_nodes", "workflow_edges", "artifact_references"), True))
    return mutations
