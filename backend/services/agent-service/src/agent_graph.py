# HydroGuardian agent-service MVP 的 LangGraph 拓扑定义。
# 节点实现放在 nodes/ 中；本文件只声明执行顺序。

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from nodes.change import change_detection_node
from nodes.evidence import evidence_execution_node
from nodes.program import program_builder_node
from nodes.recommendation import recommendation_node
from nodes.risk import risk_assessment_node
from nodes.scene import scene_data_adapter_node
from nodes.task import task_parser_node
from nodes.work_order import work_order_node
from state import AgentState


# 主流程先保持线性，方便联调和排查。像 review-required、abstain
# 这类提前退出分支先通过 state/status 编码，由各节点自己处理。
graph_builder = StateGraph(AgentState)

# 任务理解和 program 构建负责把自然语言转成可执行的 field-schema program。
graph_builder.add_node("parse_task", task_parser_node)
graph_builder.add_node("build_program", program_builder_node)

# 场景准备和证据执行负责连接算法服务。
graph_builder.add_node("prepare_scene_sample", scene_data_adapter_node)
graph_builder.add_node("execute_3d", evidence_execution_node)
graph_builder.add_node("maybe_detect_change", change_detection_node)

# 风险、建议和工单节点负责把证据转成业务输出。
graph_builder.add_node("assess_risk", risk_assessment_node)
graph_builder.add_node("generate_recommendation", recommendation_node)
graph_builder.add_node("create_work_order", work_order_node)

# MVP 阶段有意保持线性边；每个节点仍可把 state.status 降级为
# FAILED、ABSTAINED 或 REVIEW_REQUIRED。
graph_builder.add_edge(START, "parse_task")
graph_builder.add_edge("parse_task", "build_program")
graph_builder.add_edge("build_program", "prepare_scene_sample")
graph_builder.add_edge("prepare_scene_sample", "execute_3d")
graph_builder.add_edge("execute_3d", "maybe_detect_change")
graph_builder.add_edge("maybe_detect_change", "assess_risk")
graph_builder.add_edge("assess_risk", "generate_recommendation")
graph_builder.add_edge("generate_recommendation", "create_work_order")
graph_builder.add_edge("create_work_order", END)
graph = graph_builder.compile()
