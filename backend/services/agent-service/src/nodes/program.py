from __future__ import annotations

from config import LABEL_IDS
from state import AgentState, append_error, append_trace


def label_ids_for(names: list[str]) -> list[int]:
    ids: list[int] = []
    for name in names:
        label_id = LABEL_IDS.get(name)
        if label_id is not None and label_id not in ids:
            ids.append(label_id)
    return ids


def program_builder_node(state: AgentState) -> AgentState:
    intent = state["task_intent"]
    if intent.get("needs_clarification"):
        state["status"] = "REVIEW_REQUIRED"
        append_error(state, "build_program", "task needs clarification")
        return state
    if intent.get("needs_abstain"):
        state["status"] = "ABSTAINED"
        append_error(state, "build_program", "task is outside the current executable scope")
        return state

    # 从这里开始，任务意图会被“翻译”成 hydro-program3d 可执行的 program。
    # 这一步是系统从自然语言走向空间执行的关键桥梁。
    target = str(intent.get("target", "disturbance"))
    relations = []
    for relation in intent.get("relations", []):
        reference = str(relation.get("reference", ""))
        enriched = dict(relation)
        # hydro-program3d 要求 reference / negative 都带显式 label id，
        # 所以在这里把任务解析结果补齐，而不是留给下游服务端兜底。
        enriched["reference_label_ids"] = label_ids_for([reference])
        relations.append(enriched)

    negatives = [str(item) for item in intent.get("negatives", [])]
    # program 结构尽量直接对齐 hydro-program3d /execute 的 field schema，
    # 这样客户端层就不需要再写一层复杂适配。
    program = {
        "program_schema_mode": "field",
        "program_version": "v1_field",
        "target": target,
        "target_label_ids": label_ids_for([target]),
        "attributes": list(intent.get("attributes", [])),
        "relations": relations,
        "negatives": negatives,
        "negative_label_ids": label_ids_for(negatives),
        "evidence": ["geometry", "ortho_edge"],
        "metadata": {"task_id": state["task_id"], "scene_id": state["scene_id"]},
        "source_text": intent.get("source_text", state["task_text"]),
    }
    bundle = {
        "bundle_type": "program_bundle",
        "source_text": state["task_text"],
        "selected_candidate_id": "c0",
        # 当前 MVP 只构造一个候选。以后如果要做多候选 program 排序，
        # 可以先从这里扩成多个 candidate。
        "candidates": [
            {
                "candidate_id": "c0",
                "program": program,
                "proposal_score": 1.0,
                "proposal_source": "rule_task_compiler",
            }
        ],
    }

    state["selected_program"] = program
    state["program_bundle"] = bundle
    state["status"] = "PROGRAM_READY"
    append_trace(
        state,
        "build_program",
        "program bundle built",
        {"target": target, "target_label_ids": program["target_label_ids"]},
    )
    return state
