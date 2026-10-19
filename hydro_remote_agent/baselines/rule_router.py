from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple


CLASS_ALIASES = {
    1: ("shed", "棚屋"),
    2: ("concretehouse", "concrete house", "混凝土房屋", "混凝土建筑"),
    3: ("cementroad", "cement road", "水泥路"),
    4: ("dirtroad", "dirt road", "unpaved road", "土路", "未铺装道路"),
    5: ("slope", "边坡"),
    6: ("scarp", "陡坎"),
    7: ("dam", "堤坝", "坝体"),
    8: ("vegetablefield", "vegetable field", "菜地"),
    9: ("grassland", "草地"),
    10: ("dryland", "旱地"),
    11: ("woodland", "林地"),
    12: ("bareland", "bare land", "裸地"),
    13: ("waterline", "water line", "水线"),
    14: ("ditch", "沟渠"),
    15: ("others", "other class", "其他类别"),
}

RELATION_ALIASES = {
    "near": (" near ", "nearby", "adjacent", "proximity", "close to", "附近", "邻近", "靠近", "相邻"),
    "above": (" above ", "higher than", "overlying", "上方", "高于", "之上"),
}

SEGMENTATION_CUES = (
    "segment", "extract", "delineat", "mask", "point-level", "point cloud",
    "point coordinates", "localized points", "spatial distribution", "spatial localization",
    "分割", "提取", "掩膜", "点云", "点级", "点位", "定位", "空间分布", "坐标集合",
)

ATTRIBUTE_CUES = (
    "attribute", "matching", "condition", "satisfy", "consistent with", "characteristic",
    "forms unbroken", "contiguous", "broad extent", "well-defined", "属性", "特征", "条件",
    "连续", "成片", "轮廓", "形态",
)

NO_TARGET_CUES = (
    "if none", "if absent", "if no ", "even if none", "or indicate absence",
    "or indicate no", "return an empty", "empty result", "no output", "若无", "如果没有",
    "如无", "不存在", "为空", "无结果",
)

FULL_SCENE_CUES = (
    "all 15 classes", "full semantic", "full scene", "every point in the dataset",
    "全部15个类别", "所有15个类别", "全场景", "完整语义分类",
)


@dataclass(frozen=True)
class RuleRouterResult:
    request: Dict[str, Any]
    trace: Dict[str, Any]


def _user_payload(record: Mapping[str, Any]) -> Dict[str, Any]:
    messages = record.get("messages")
    if not isinstance(messages, list):
        raise ValueError("record messages must be a list")
    for message in messages:
        if isinstance(message, Mapping) and message.get("role") == "user":
            payload = json.loads(str(message.get("content", "")))
            if not isinstance(payload, dict):
                break
            return payload
    raise ValueError("record has no JSON user payload")


def _contains(text: str, cues: Sequence[str]) -> bool:
    return any(cue in text for cue in cues)


def _classes_in_query(text: str) -> List[int]:
    matches: List[Tuple[int, int]] = []
    for class_id, aliases in CLASS_ALIASES.items():
        positions = [text.find(alias) for alias in aliases if alias in text]
        if positions:
            matches.append((min(positions), class_id))
    matches.sort()
    return [class_id for _, class_id in matches]


def _relation_in_query(text: str) -> str | None:
    padded = f" {text} "
    for relation, aliases in RELATION_ALIASES.items():
        if _contains(padded, aliases):
            return relation
    return None


def _direct_answer(query: str) -> str:
    if re.search(r"\b(no|not|without|absent)\b", query.lower()):
        return "The requested condition cannot be confirmed from the supplied scene."
    return "Yes. The requested scene condition is present."


class RuleRouter:
    """Deterministic text-only lower bound with no access to IDs or gold metadata."""

    version = "rule_router.v1"

    def plan(self, record: Mapping[str, Any]) -> RuleRouterResult:
        started = time.perf_counter()
        payload = _user_payload(record)
        query = str(payload.get("query", "")).strip()
        assets = payload.get("assets")
        if not query or not isinstance(assets, Mapping):
            raise ValueError("user payload requires query and assets")
        text = query.casefold()
        class_ids = _classes_in_query(text)
        relation = _relation_in_query(text)
        segmentation = _contains(text, SEGMENTATION_CUES)
        full_scene = _contains(text, FULL_SCENE_CUES)
        attribute = _contains(text, ATTRIBUTE_CUES)
        no_target = _contains(text, NO_TARGET_CUES)

        image_path = str(assets.get("image_path", ""))
        point_cloud_path = str(assets.get("point_cloud_path", ""))
        request_id = str(payload.get("request_id", ""))
        matched_rules: List[str] = []

        if full_scene:
            matched_rules.append("full_scene")
            request = self._full_scene(request_id, image_path, point_cloud_path)
        elif relation and segmentation:
            matched_rules.extend(("relation", "segmentation"))
            request = self._relation_workflow(
                request_id, image_path, point_cloud_path, relation, class_ids
            )
        elif segmentation:
            matched_rules.append("segmentation")
            if attribute:
                matched_rules.append("attribute")
            if no_target:
                matched_rules.append("no_target")
            request = self._segmentation_call(
                request_id, query, image_path, point_cloud_path, class_ids, attribute or no_target
            )
        else:
            matched_rules.append("direct_answer")
            intent = (
                "relation_judgement" if relation else
                "attribute_judgement" if attribute else
                "class_presence"
            )
            request = {
                "schema_version": "1.0",
                "request_id": request_id,
                "intent": intent,
                "action": {"type": "direct_answer", "answer": _direct_answer(query)},
                "expected_output": {"type": "text", "coordinate_space": "none"},
            }

        return RuleRouterResult(
            request=request,
            trace={
                "router_version": self.version,
                "matched_rules": matched_rules,
                "detected_class_ids": class_ids,
                "detected_relation": relation,
                "latency_seconds": time.perf_counter() - started,
                "input_fields": ["messages.user.content.query", "messages.user.content.assets"],
            },
        )

    @staticmethod
    def _full_scene(request_id: str, image_path: str, point_cloud_path: str) -> Dict[str, Any]:
        return {
            "schema_version": "1.0", "request_id": request_id,
            "intent": "full_scene_segmentation",
            "action": {"type": "tool_call", "tool": "multimodal_semantic_segmentation",
                       "arguments": {"image_path": image_path, "point_cloud_path": point_cloud_path,
                                     "return_probabilities": True}, "verification": "required"},
            "expected_output": {"type": "point_labels", "coordinate_space": "source_point_cloud"},
        }

    @staticmethod
    def _segmentation_call(request_id: str, query: str, image_path: str,
                           point_cloud_path: str, class_ids: Sequence[int],
                           language_guided: bool) -> Dict[str, Any]:
        target_ids = list(class_ids[:1])
        if language_guided:
            tool = "language_guided_point_segmentation"
            arguments: Dict[str, Any] = {"image_path": image_path, "point_cloud_path": point_cloud_path,
                                         "query": query, "return_probabilities": True}
            if target_ids:
                arguments["target_class_ids"] = target_ids
            intent = "attribute_segmentation" if _contains(query.casefold(), ATTRIBUTE_CUES) else "class_segmentation"
            result_type = "point_mask"
        else:
            tool = "multimodal_semantic_segmentation"
            arguments = {"image_path": image_path, "point_cloud_path": point_cloud_path,
                         "target_class_ids": target_ids, "return_probabilities": True}
            intent = "class_segmentation"
            result_type = "point_labels"
        return {
            "schema_version": "1.0", "request_id": request_id, "intent": intent,
            "action": {"type": "tool_call", "tool": tool, "arguments": arguments,
                       "verification": "required"},
            "expected_output": {"type": result_type, "coordinate_space": "source_point_cloud"},
        }

    @staticmethod
    def _relation_workflow(request_id: str, image_path: str, point_cloud_path: str,
                           relation: str, class_ids: Sequence[int]) -> Dict[str, Any]:
        target_id = int(class_ids[0]) if class_ids else 15
        reference_id = int(class_ids[1]) if len(class_ids) > 1 else target_id
        segment_ids = list(dict.fromkeys((target_id, reference_id)))
        geometry_arguments: Dict[str, Any] = {
            "point_cloud_path": point_cloud_path,
            "segmentation_result_path": "${segment.artifacts.point_labels}",
            "operation": relation, "target_class_id": target_id,
            "reference_class_id": reference_id,
        }
        geometry_arguments["distance_threshold_m" if relation == "near" else "z_margin_m"] = 3.0 if relation == "near" else 0.2
        return {
            "schema_version": "1.0", "request_id": request_id,
            "intent": "relation_segmentation",
            "action": {"type": "workflow", "steps": [
                {"step_id": "segment", "tool": "multimodal_semantic_segmentation",
                 "arguments": {"image_path": image_path, "point_cloud_path": point_cloud_path,
                               "target_class_ids": segment_ids, "return_probabilities": True},
                 "depends_on": [], "verification": "required"},
                {"step_id": "relation", "tool": "geometry_relation_analysis",
                 "arguments": geometry_arguments, "depends_on": ["segment"],
                 "verification": "required"},
            ]},
            "expected_output": {"type": "point_mask", "coordinate_space": "source_point_cloud"},
        }
