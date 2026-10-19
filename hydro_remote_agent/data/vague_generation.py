from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


PROMPT_VERSION = "vague_hydro_l0_l3_bilingual_v5"
VALID_LEVELS = ("L0", "L1", "L2", "L3")
VALID_LANGUAGES = {"en", "zh"}
SPLIT_PRIORITY = {"test": 0, "val": 1, "train": 2}
FORBIDDEN_TOOL_TERMS = (
    "point_semantic_segmentation",
    "multimodal_semantic_segmentation",
    "image_change_detection",
    "language_guided_point_segmentation",
    "geometry_relation_analysis",
    "result_quality_verification",
)
JUDGEMENT_INTENTS = {
    "class_presence",
    "attribute_judgement",
    "relation_judgement",
}
POINT_OUTPUT_CUES = {
    "en": re.compile(r"\b(point|points|point-level|pointwise|point-cloud|3d)\b", re.IGNORECASE),
    "zh": re.compile(r"(点云|点级|逐点|点位|点集|点)"),
}
POINT_OUTPUT_CONFLICTS = {
    "en": re.compile(r"\b(pixel|pixels|vectorize|vectorized|vectorization)\b", re.IGNORECASE),
    "zh": re.compile(r"(像素|矢量化|矢量勾绘|矢量边界)"),
}
JUDGEMENT_ACTION_CONFLICTS = {
    "en": re.compile(
        r"\b(where|locate|localize|map|segment|mask|extract|"
        r"delineate|mark|describe)\b",
        re.IGNORECASE,
    ),
    "zh": re.compile(
        r"(哪里|何处|具体位置|位于哪里|位于何处|请定位|定位出|指出.+位置|"
        r"标出|提取|分割|掩膜|勾绘|描述其分布|分布区域)"
    ),
}
CLASS_TERMS = {
    "en": {
        1: ("shed",),
        2: ("concretehouse", "concrete house"),
        3: ("cementroad", "cement road"),
        4: ("dirtroad", "dirt road", "unpaved road"),
        5: ("slope",),
        6: ("scarp",),
        7: ("dam",),
        8: ("vegetablefield", "vegetable field"),
        9: ("grassland",),
        10: ("dryland", "dry land"),
        11: ("woodland",),
        12: ("bareland", "bare land"),
        13: ("waterline", "water line", "water boundary"),
        14: ("ditch", "drainage ditch"),
        15: ("others", "other class"),
    },
    "zh": {
        1: ("棚屋", "棚房"),
        2: ("混凝土房屋",),
        3: ("水泥路",),
        4: ("土路", "未铺装道路"),
        5: ("边坡",),
        6: ("陡坎",),
        7: ("堤坝", "坝体"),
        8: ("菜地",),
        9: ("草地",),
        10: ("旱地",),
        11: ("林地",),
        12: ("裸地",),
        13: ("水线", "水体边界"),
        14: ("沟渠", "排水沟"),
        15: ("其他类别", "其他地物"),
    },
}


class VagueGenerationError(ValueError):
    """Raised when generated language changes or invalidates a gold action."""


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def semantic_signature(record: Mapping[str, Any]) -> Dict[str, Any]:
    supervision = record.get("supervision")
    if not isinstance(supervision, dict):
        raise VagueGenerationError("canonical record supervision must be an object")
    rule = supervision.get("target_mask_rule")
    relation = str(rule.get("type")) if isinstance(rule, dict) and rule.get("type") else None
    attributes = list(
        dict.fromkeys(
            str(value)
            for field in ("attributes", "attribute_phrases")
            for value in supervision.get(field, [])
        )
    )
    return {
        "intent": str(record.get("canonical_intent", "")),
        "output_granularity": str(record.get("output_granularity", "")),
        "target_label_ids": [int(value) for value in supervision.get("target_label_ids", [])],
        "target_label_names": [str(value) for value in supervision.get("target_label_names", [])],
        "attributes": attributes,
        "reference_label_ids": [
            int(value) for value in supervision.get("reference_label_ids", [])
        ],
        "reference_label_names": [
            str(value) for value in supervision.get("reference_label_names", [])
        ],
        "relation": relation,
        "is_no_target": bool(supervision.get("is_no_target", False)),
    }


def generation_input_fingerprint(record: Mapping[str, Any]) -> str:
    return sha256(
        {
            "canonical_query": str(record.get("query", "")),
            "semantic_signature": semantic_signature(record),
        }
    )


def _approved_class_terms(label_ids: Sequence[int], language: str) -> Dict[str, List[str]]:
    return {
        str(label_id): list(CLASS_TERMS[language].get(int(label_id), ()))
        for label_id in label_ids
    }


def _split_style(split: str) -> str:
    if split == "train":
        return (
            "Use broad everyday and professional wording diversity. L2 and L3 may use "
            "inspection, screening, maintenance, or risk-review contexts."
        )
    if split == "val":
        return (
            "Use concise validation-only syntax. Avoid stock phrases such as 'please identify', "
            "'segment every point', and 'is there'."
        )
    if split == "test":
        return (
            "Use held-out field-practitioner wording with indirect goals and varied sentence "
            "structure. Do not copy the canonical query or common training-style commands."
        )
    raise VagueGenerationError(f"unsupported split {split!r}")


def build_generation_prompt(
    records: Sequence[Mapping[str, Any]],
    language: str,
) -> Tuple[str, str]:
    if language not in VALID_LANGUAGES:
        raise VagueGenerationError(f"unsupported language {language!r}")
    if not records:
        raise VagueGenerationError("generation batch cannot be empty")
    split = str(records[0].get("split", ""))
    if any(str(record.get("split", "")) != split for record in records):
        raise VagueGenerationError("a generation batch cannot mix dataset splits")

    language_instruction = (
        "Write every query in natural English."
        if language == "en"
        else "所有 query 必须使用自然、专业且通顺的中文。"
    )
    tasks = [
        {
            "parent_query_id": str(record["query_id"]),
            "canonical_query": str(record["query"]),
            "semantic_signature": semantic_signature(record),
            "required_output_cues": (
                ["point", "points", "point-level", "pointwise", "point-cloud", "3D"]
                if language == "en"
                and semantic_signature(record)["output_granularity"] == "point_mask"
                else (
                    ["点云", "点级", "逐点", "点位", "点集", "点"]
                    if semantic_signature(record)["output_granularity"] == "point_mask"
                    else []
                )
            ),
            "approved_target_terms": _approved_class_terms(
                semantic_signature(record)["target_label_ids"],
                language,
            ),
            "approved_reference_terms": _approved_class_terms(
                semantic_signature(record)["reference_label_ids"],
                language,
            ),
        }
        for record in records
    ]
    system_prompt = (
        "You create user queries for a hydrological remote-sensing Agent dataset. "
        "Preserve the requested task, targets, relation, no-target state, and output granularity "
        "exactly. Never answer the query. Never mention internal tool or model names. "
        "Never silently switch between point-cloud points, image pixels, raster masks, vectors, "
        "text judgements, or localization tasks. "
        "Return one valid JSON object and no reasoning."
    )
    user_prompt = f"""
Generate four semantically equivalent user queries for each task.

Language: {language}
{language_instruction}
Split-specific style: {_split_style(split)}

Levels:
- L0: explicit target and requested output.
- L1: natural paraphrase with aliases, but still operationally clear.
- L2: scenario need; hide algorithm names while preserving the required output granularity.
- L3: field inspection, engineering review, or risk-screening goal; indirect but unambiguous.

Rules:
1. Do not reveal whether a target is actually present or absent.
2. A text answer request must remain a text judgement; a point-mask request must still ask for
   point-level localization in every level; a full-scene label request must still request a
   complete map. Never call point-cloud points pixels, raster cells, or vectors.
   For every point_mask task, each L0/L1/L2/L3 query MUST literally contain at least one token
   from that task's required_output_cues. English words such as area, extent, map, region, or
   location do NOT satisfy this rule by themselves. This requirement also applies to indirect
   L2/L3 field scenarios.
3. Do not invent classes, attributes, relations, distances, dates, or modalities.
4. Presence/judgement tasks must remain yes/no or confirmation requests. Do not turn them into
   where/locate/describe/segment requests.
5. Do not narrow or broaden a class or attribute. For example, woodland must not become
   broadleaf forest, and a ditch must not become a generic hydraulic feature.
6. Every variant must explicitly contain one approved_target_term for every target class and,
   for relation tasks, one approved_reference_term for every reference class. Inflect surrounding
   grammar freely, but do not replace these controlled terms with narrower or broader classes.
7. Do not use any of these internal names: {", ".join(FORBIDDEN_TOOL_TERMS)}.
8. Return exactly one item per input and exactly one variant for each L0/L1/L2/L3.
9. Copy semantic_signature exactly into semantic_check.

Output schema:
{{
  "items": [
    {{
      "parent_query_id": "...",
      "semantic_check": {{...exact semantic_signature...}},
      "variants": [
        {{"level": "L0", "query": "..."}},
        {{"level": "L1", "query": "..."}},
        {{"level": "L2", "query": "..."}},
        {{"level": "L3", "query": "..."}}
      ]
    }}
  ]
}}

Input tasks:
{json.dumps(tasks, ensure_ascii=False, indent=2)}
""".strip()
    return system_prompt, user_prompt


def _normalize_query(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _has_expected_language(text: str, language: str) -> bool:
    cjk_count = sum("\u4e00" <= char <= "\u9fff" for char in text)
    if language == "zh":
        return cjk_count >= 2
    return cjk_count == 0


def _validate_query_contract(
    query: str,
    record: Mapping[str, Any],
    language: str,
    level: str,
) -> None:
    output_granularity = str(record.get("output_granularity", ""))
    intent = str(record.get("canonical_intent", ""))
    if output_granularity == "point_mask":
        if POINT_OUTPUT_CONFLICTS[language].search(query):
            raise VagueGenerationError(
                f"{record['query_id']}/{level} changes point output to pixels or vectors"
            )
        if not POINT_OUTPUT_CUES[language].search(query):
            raise VagueGenerationError(
                f"{record['query_id']}/{level} does not explicitly request point-level output"
            )
    if intent in JUDGEMENT_INTENTS and JUDGEMENT_ACTION_CONFLICTS[language].search(query):
        raise VagueGenerationError(
            f"{record['query_id']}/{level} changes a judgement into localization or description: "
            f"{query!r}"
        )
    signature = semantic_signature(record)
    normalized_query = query.casefold()
    for role, label_ids in (
        ("target", signature["target_label_ids"]),
        ("reference", signature["reference_label_ids"]),
    ):
        for label_id in label_ids:
            terms = CLASS_TERMS[language].get(int(label_id), ())
            if not terms or not any(term.casefold() in normalized_query for term in terms):
                raise VagueGenerationError(
                    f"{record['query_id']}/{level} omits the controlled {role} class "
                    f"term for label {label_id}"
                )


def validate_generation_payload(
    payload: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    language: str,
) -> Dict[str, Dict[str, Any]]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise VagueGenerationError("LLM payload.items must be a list")
    expected = {str(record["query_id"]): record for record in records}
    output: Dict[str, Dict[str, Any]] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise VagueGenerationError("LLM payload items must be objects")
        parent_id = str(raw_item.get("parent_query_id", ""))
        if parent_id not in expected:
            raise VagueGenerationError(f"unexpected parent_query_id {parent_id!r}")
        if parent_id in output:
            raise VagueGenerationError(f"duplicate parent_query_id {parent_id!r}")
        expected_signature = semantic_signature(expected[parent_id])
        if raw_item.get("semantic_check") != expected_signature:
            raise VagueGenerationError(f"semantic signature drift for {parent_id}")
        variants = raw_item.get("variants")
        if not isinstance(variants, list) or len(variants) != len(VALID_LEVELS):
            raise VagueGenerationError(f"{parent_id} must contain exactly four variants")
        by_level: Dict[str, str] = {}
        normalized_queries = set()
        for variant in variants:
            if not isinstance(variant, dict):
                raise VagueGenerationError(f"{parent_id} variants must be objects")
            level = str(variant.get("level", ""))
            query = str(variant.get("query", "")).strip()
            if level not in VALID_LEVELS or level in by_level:
                raise VagueGenerationError(f"{parent_id} has invalid or duplicate level {level!r}")
            if len(query) < 4:
                raise VagueGenerationError(f"{parent_id}/{level} query is too short")
            if not _has_expected_language(query, language):
                raise VagueGenerationError(
                    f"{parent_id}/{level} does not match language {language}"
                )
            normalized = _normalize_query(query)
            if normalized in normalized_queries:
                raise VagueGenerationError(f"{parent_id} contains duplicate query variants")
            if any(term in normalized for term in FORBIDDEN_TOOL_TERMS):
                raise VagueGenerationError(f"{parent_id}/{level} leaks an internal tool name")
            _validate_query_contract(query, expected[parent_id], language, level)
            normalized_queries.add(normalized)
            by_level[level] = query
        if set(by_level) != set(VALID_LEVELS):
            raise VagueGenerationError(f"{parent_id} is missing an ambiguity level")
        output[parent_id] = {
            "parent_query_id": parent_id,
            "semantic_check": expected_signature,
            "variants": [{"level": level, "query": by_level[level]} for level in VALID_LEVELS],
        }
    missing = sorted(set(expected) - set(output))
    if missing:
        raise VagueGenerationError(f"LLM payload is missing parent IDs: {missing}")
    return output


def materialize_variants(
    canonical_record: Mapping[str, Any],
    generated_item: Mapping[str, Any],
    language: str,
    model: str,
    response_id: Optional[str],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    parent_id = str(canonical_record["query_id"])
    for variant in generated_item["variants"]:
        level = str(variant["level"])
        output = dict(canonical_record)
        output["query_id"] = f"{parent_id}:{language}:{level.lower()}"
        output["language"] = language
        output["ambiguity_level"] = level
        output["query"] = str(variant["query"])
        gold_request = dict(output["gold_request"])
        gold_request["request_id"] = output["query_id"]
        output["gold_request"] = gold_request
        provenance = dict(output["provenance"])
        provenance.update(
            {
                "parent_query_id": parent_id,
                "generation_type": "llm_vague_query",
                "prompt_version": PROMPT_VERSION,
                "model": model,
                "response_id": response_id,
            }
        )
        output["provenance"] = provenance
        records.append(output)
    return records


def semantic_key(record: Mapping[str, Any]) -> str:
    return sha256(semantic_signature(record))


def deduplicate_exact_queries(
    records: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    ordered = sorted(
        enumerate(records),
        key=lambda item: (
            SPLIT_PRIORITY.get(str(item[1].get("split", "")), 99),
            item[0],
        ),
    )
    kept: List[Tuple[int, Dict[str, Any]]] = []
    seen: Dict[Tuple[str, str, str], Tuple[str, str, str]] = {}
    cross_scene_queries: Dict[Tuple[str, str], set[str]] = {}
    dropped: List[Dict[str, str]] = []
    conflicts: List[Dict[str, str]] = []
    for original_index, raw_record in ordered:
        record = dict(raw_record)
        language = str(record.get("language", ""))
        sample_id = str(record.get("sample_id", ""))
        normalized = _normalize_query(str(record.get("query", "")))
        key = (sample_id, language, normalized)
        cross_scene_queries.setdefault((language, normalized), set()).add(sample_id)
        signature = semantic_key(record)
        split = str(record.get("split", ""))
        previous = seen.get(key)
        if previous is None:
            seen[key] = (signature, str(record["query_id"]), split)
            kept.append((original_index, record))
            continue
        previous_signature, previous_id, previous_split = previous
        item = {
            "query_id": str(record["query_id"]),
            "duplicate_of": previous_id,
            "query": str(record["query"]),
        }
        if previous_signature != signature:
            conflicts.append(item)
        elif previous_split == split:
            kept.append((original_index, record))
        else:
            dropped.append(item)
    if conflicts:
        raise VagueGenerationError(
            f"{len(conflicts)} identical queries map to different semantic actions; "
            f"examples: {conflicts[:5]}"
        )
    kept.sort(key=lambda item: item[0])
    cross_scene_duplicate_count = sum(
        1 for sample_ids in cross_scene_queries.values() if len(sample_ids) > 1
    )
    return [record for _, record in kept], {
        "input_count": len(records),
        "kept_count": len(kept),
        "dropped_exact_duplicate_count": len(dropped),
        "dropped_examples": dropped[:20],
        "semantic_conflict_count": 0,
        "cross_scene_exact_query_count": cross_scene_duplicate_count,
    }


class GenerationCache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            timeout=60.0,
        )
        self._connection.execute("PRAGMA busy_timeout = 60000")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS vague_generation (
                cache_key TEXT PRIMARY KEY,
                parent_query_id TEXT NOT NULL,
                language TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                response_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    @staticmethod
    def key(
        parent_query_id: str,
        language: str,
        model: str,
        input_fingerprint: Optional[str] = None,
    ) -> str:
        return sha256(
            {
                "parent_query_id": parent_query_id,
                "language": language,
                "model": model,
                "prompt_version": PROMPT_VERSION,
                "input_fingerprint": input_fingerprint,
            }
        )

    def get(
        self,
        parent_query_id: str,
        language: str,
        model: str,
        input_fingerprint: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        cache_key = self.key(parent_query_id, language, model, input_fingerprint)
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json, response_id FROM vague_generation WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return {"item": json.loads(row[0]), "response_id": row[1]}

    def set(
        self,
        parent_query_id: str,
        language: str,
        model: str,
        item: Mapping[str, Any],
        response_id: Optional[str],
        input_fingerprint: Optional[str] = None,
    ) -> None:
        cache_key = self.key(parent_query_id, language, model, input_fingerprint)
        with self._lock:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO vague_generation(
                    cache_key, parent_query_id, language, model, prompt_version,
                    payload_json, response_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    parent_query_id,
                    language,
                    model,
                    PROMPT_VERSION,
                    canonical_json(item),
                    response_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._connection.commit()

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM vague_generation"
            ).fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        with self._lock:
            self._connection.close()
