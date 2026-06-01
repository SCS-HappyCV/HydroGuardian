from __future__ import annotations

from typing import Any, Dict, Iterable

from state import AgentState

#放任务理解规范：允许类别、属性、关系、别名归一化、tool schema、system prompt、task_intent 标准化。
ALLOWED_CLASSES = [
    "shed",
    "concrete house",
    "cement road",
    "road",
    "dirt road",
    "slope",
    "scarp",
    "dam",
    "vegetable field",
    "grassland",
    "dryland",
    "woodland",
    "bareland",
    "waterline",
    "ditch",
    "others",
]
ALLOWED_ATTRIBUTES = [
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
]
ALLOWED_RELATIONS = ["near", "adjacent", "along", "above", "below"]

LABEL_ALIASES = {
    "沟渠": "ditch",
    "ditch": "ditch",
    "ditches": "ditch",
    "水线": "waterline",
    "水边线": "waterline",
    "water line": "waterline",
    "waterline": "waterline",
    "water edge": "waterline",
    "道路": "road",
    "路": "road",
    "road": "road",
    "roads": "road",
    "水泥路": "cement road",
    "cement road": "cement road",
    "土路": "dirt road",
    "dirt road": "dirt road",
    "坡": "slope",
    "边坡": "slope",
    "陡坡": "slope",
    "slope": "slope",
    "steep slope": "slope",
    "steep_slope": "slope",
    "陡坎": "scarp",
    "scarp": "scarp",
    "坝体": "dam",
    "大坝": "dam",
    "dam": "dam",
    "裸地": "bareland",
    "bareland": "bareland",
    "bare land": "bareland",
    "草地": "grassland",
    "grassland": "grassland",
    "林地": "woodland",
    "woodland": "woodland",
    "旱地": "dryland",
    "dryland": "dryland",
    "vegetable field": "vegetable field",
    "菜地": "vegetable field",
    "房屋": "concrete house",
    "concrete house": "concrete house",
    "棚": "shed",
    "shed": "shed",
    "others": "others",
    "other": "others",
    "disturbance": "disturbance",
}
ATTRIBUTE_ALIASES = {
    "细": "thin",
    "狭窄": "thin",
    "窄": "thin",
    "thin": "thin",
    "细长": "linear",
    "线状": "linear",
    "linear": "linear",
    "elongated": "linear",
    "平坦": "flat",
    "flat": "flat",
    "陡": "steep",
    "陡坡": "steep",
    "steep": "steep",
    "低洼": "low_elevation",
    "低高程": "low_elevation",
    "low elevation": "low_elevation",
    "low_elevation": "low_elevation",
    "高程较高": "high_elevation",
    "高高程": "high_elevation",
    "high elevation": "high_elevation",
    "high_elevation": "high_elevation",
    "近水": "water_related",
    "涉水": "water_related",
    "water related": "water_related",
    "water_related": "water_related",
    "植被": "vegetated",
    "vegetated": "vegetated",
    "裸地": "bare_ground",
    "bare": "bare_ground",
    "bare ground": "bare_ground",
    "bare_ground": "bare_ground",
    "建筑": "built",
    "built": "built",
}
RELATION_ALIASES = {
    "近": "near",
    "附近": "near",
    "靠近": "near",
    "近水": "near",
    "near": "near",
    "adjacent": "adjacent",
    "相邻": "adjacent",
    "沿": "along",
    "沿着": "along",
    "along": "along",
    "高于": "above",
    "上方": "above",
    "above": "above",
    "低于": "below",
    "下方": "below",
    "below": "below",
}
RELATION_EVIDENCE = {
    "near": ["geometry", "xy_distance"],
    "adjacent": ["geometry", "xy_distance"],
    "along": ["geometry", "xy_distance"],
    "above": ["z_norm", "slope"],
    "below": ["z_norm", "slope"],
}
TEMPORAL_KEYWORDS = ["变化", "新增", "扩大", "历史", "对比", "前后", "change", "new", "expanded"]

TASK_PARSE_TOOL = {
    "type": "function",
    "function": {
        "name": "parse_hydro_task",
        "description": "Parse a hydrological inspection task into structured intent fields for HydroGuardian.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "goal": {"type": "string"},
                "intent_type": {"type": "string"},
                "target": {"type": "string"},
                "attributes": {"type": "array", "items": {"type": "string"}},
                "relations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "type": {"type": "string"},
                            "reference": {"type": "string"},
                            "distance_m": {"type": ["number", "null"]},
                            "margin_m": {"type": ["number", "null"]},
                            "evidence": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["type", "reference", "distance_m", "margin_m", "evidence"],
                    },
                },
                "negatives": {"type": "array", "items": {"type": "string"}},
                "needs_clarification": {"type": "boolean"},
                "clarification_question": {"type": "string"},
                "needs_abstain": {"type": "boolean"},
                "abstain_reason": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
                "temporal_intent": {"type": "boolean"},
            },
            "required": [
                "goal",
                "intent_type",
                "target",
                "attributes",
                "relations",
                "negatives",
                "needs_clarification",
                "clarification_question",
                "needs_abstain",
                "abstain_reason",
                "priority",
                "temporal_intent",
            ],
        },
    },
}


SYSTEM_PROMPT = f"""你是 HydroGuardian 的水利巡查任务理解器。

你必须调用 parse_hydro_task 工具，把用户自然语言任务解析成结构化字段。

允许的目标类别:
{", ".join(ALLOWED_CLASSES)}

允许的属性:
{", ".join(ALLOWED_ATTRIBUTES)}

允许的空间关系:
{", ".join(ALLOWED_RELATIONS)}

规则:
- target 必须是单个目标；优先选择真正要筛查的风险对象。
- attributes 只放目标自身属性，例如 thin、linear、steep、bare_ground。
- relations 放目标和参考物之间的空间关系，例如 ditch near waterline。
- negatives 放需要排除或容易混淆的类别，例如 road、cement road、dirt road。
- temporal_intent 只有在用户提到历史、变化、新增、扩大、前后对比时才为 true。
- 如果任务缺少 scene_id 或目标完全不清楚，可 needs_clarification=true。
- 如果任务明显超出水利隐患筛查范围，可 needs_abstain=true。
- 不要编造不存在的类别、属性或关系。
"""


def unique_list(values: Iterable[str]) -> list[str]:
    seen = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def clean_key(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def canonical_label(value: Any) -> str | None:
    text = clean_key(str(value))
    if text in ALLOWED_CLASSES:
        return text
    return LABEL_ALIASES.get(text)


def canonical_attribute(value: Any) -> str | None:
    text = clean_key(str(value))
    if text in ALLOWED_ATTRIBUTES:
        return text
    return ATTRIBUTE_ALIASES.get(text)


def canonical_relation(value: Any) -> str | None:
    text = clean_key(str(value))
    if text in ALLOWED_RELATIONS:
        return text
    return RELATION_ALIASES.get(text)


def normalize_temporal_intent(text: str) -> bool:
    text_lower = text.lower()
    return any(keyword in text_lower or keyword in text for keyword in TEMPORAL_KEYWORDS)


def normalize_negatives(values: Any) -> list[str]:
    negatives: list[str] = []
    for item in as_list(values):
        canonical = canonical_label(item)
        if canonical == "road":
            negatives.extend(["cement road", "dirt road"])
        elif canonical and canonical not in {"disturbance", "others"}:
            negatives.append(canonical)
    return unique_list(negatives)


def normalize_relations(values: Any) -> list[Dict[str, Any]]:
    relations: list[Dict[str, Any]] = []
    for item in as_list(values):
        if not isinstance(item, dict):
            continue
        relation_type = canonical_relation(item.get("type", "near")) or "near"
        reference = canonical_label(item.get("reference", ""))
        if not reference or reference in {"disturbance", "others"}:
            continue

        distance_m = item.get("distance_m")
        margin_m = item.get("margin_m")
        if relation_type in {"near", "adjacent"} and distance_m is None:
            distance_m = 5.0
        elif relation_type == "along" and distance_m is None:
            distance_m = 4.0
        elif relation_type in {"above", "below"} and margin_m is None:
            margin_m = 0.2

        evidence = [
            str(token)
            for token in as_list(item.get("evidence"))
            if str(token).strip()
        ] or list(RELATION_EVIDENCE.get(relation_type, ["geometry"]))

        relations.append(
            {
                "type": relation_type,
                "reference": reference,
                "distance_m": distance_m,
                "margin_m": margin_m,
                "evidence": unique_list(evidence),
            }
        )
    return relations


def normalize_intent(payload: Dict[str, Any], state: AgentState, parser_source: str) -> Dict[str, Any]:
    text = state["task_text"].strip()
    target = canonical_label(payload.get("target")) or "disturbance"

    attributes = []
    for item in as_list(payload.get("attributes")):
        canonical = canonical_attribute(item)
        if canonical is not None:
            attributes.append(canonical)
    if target == "slope" and ("陡" in text or "steep" in text.lower()) and "steep" not in attributes:
        attributes.append("steep")

    relations = normalize_relations(payload.get("relations"))
    negatives = normalize_negatives(payload.get("negatives"))
    temporal_intent = bool(payload.get("temporal_intent")) or normalize_temporal_intent(text)
    needs_clarification = bool(payload.get("needs_clarification")) or not text or not state["scene_id"]
    needs_abstain = bool(payload.get("needs_abstain")) or (
        target in {"disturbance", "others"} and not relations and not attributes
    )
    priority = str(payload.get("priority", "")).lower()
    if priority not in {"low", "medium", "high"}:
        priority = "high" if relations or temporal_intent else "medium"

    return {
        "goal": str(payload.get("goal") or "water_hazard_screening"),
        "intent_type": str(payload.get("intent_type") or "inspection"),
        "target": target,
        "attributes": unique_list(attributes),
        "relations": relations,
        "negatives": negatives,
        "needs_clarification": needs_clarification,
        "clarification_question": str(payload.get("clarification_question") or ""),
        "needs_abstain": needs_abstain,
        "abstain_reason": str(payload.get("abstain_reason") or ""),
        "priority": priority,
        "temporal_intent": temporal_intent,
        "source_text": text,
        "parser_source": parser_source,
    }
