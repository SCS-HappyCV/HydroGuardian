from __future__ import annotations

from typing import Any, Dict, TypedDict


class AgentState(TypedDict):
    # 这就是整条 LangGraph 链路共享的一份“大上下文”。
    # 可以把它理解成一个会被各节点逐步补全的任务档案。
    case_id: str
    task_id: str
    task_text: str
    scene_id: str
    sample_id: str
    # task_intent: 任务理解后的结构化结果，比如目标、属性、关系、排除项。
    task_intent: Dict[str, Any]
    # program_bundle / selected_program: 给 hydro-program3d 执行的结构化 program。
    program_bundle: Dict[str, Any]
    selected_program: Dict[str, Any]
    # scene_tensor_sample: 预处理后的图像/点云/几何特征样本。
    scene_tensor_sample: Dict[str, Any]
    # raw_executor_output: /execute 原始响应，主要用于排查和追踪。
    raw_executor_output: Dict[str, Any]
    # evidence_pack: /compile_evidence 后的稳定证据对象，是风险层的主要输入。
    evidence_pack: Dict[str, Any]
    # change_pack: 变化检测结果；只有时间相关任务才会真正填充。
    change_pack: Dict[str, Any]
    # 风险卡、建议卡、工单卡是这条链路最终沉淀出的业务对象。
    risk_cards: list[Dict[str, Any]]
    recommendation_cards: list[Dict[str, Any]]
    work_orders: list[Dict[str, Any]]
    # case_result: 持久化到 case-service 之后返回的摘要。
    case_result: Dict[str, Any]
    # status: 当前任务推进到哪一步，便于节点判断是否继续、是否降级。
    status: str
    # errors / trace: 一个记错误，一个记过程，联调时非常重要。
    errors: list[Dict[str, Any]]
    trace: list[Dict[str, Any]]


def append_trace(state: AgentState, stage: str, message: str, data: Dict[str, Any] | None = None) -> None:
    # trace 用来记录“系统做了什么”，方便回放执行过程。
    item: Dict[str, Any] = {"stage": stage, "message": message}
    if data:
        item["data"] = data
    state["trace"].append(item)


def append_error(state: AgentState, stage: str, message: str, data: Dict[str, Any] | None = None) -> None:
    # error 用来记录“哪里出了问题”，但很多错误不会直接中断整条链路。
    item: Dict[str, Any] = {"stage": stage, "message": message}
    if data:
        item["data"] = data
    state["errors"].append(item)


def as_float(value: Any, default: float = 0.0) -> float:
    # 外部服务返回的数据里有时是标量，有时是单元素 list，
    # 这里统一转成 float，减少后面评分逻辑里的防御代码。
    try:
        if isinstance(value, list):
            return as_float(value[0] if value else default, default)
        return float(value)
    except (TypeError, ValueError):
        return default


def failure_evidence_pack(reason: str) -> Dict[str, Any]:
    # 失败时也返回一个“长得像 EvidencePack 的对象”。
    # 这样后续 risk / recommendation 节点还能继续跑降级逻辑。
    return {
        "status": "execution_failed",
        "target_hit": False,
        "review_required": True,
        "confidence": 0.0,
        "selected_candidate_idx": None,
        "selected_candidate_is_no_target": True,
        "selected_verifier_score": 0.0,
        "posterior_no_target_mass": 1.0,
        "abstain_probability": 1.0,
        "candidate_regions": [],
        "evidence_summary": [reason],
        "raw_trace": {"failure_reason": reason},
    }
