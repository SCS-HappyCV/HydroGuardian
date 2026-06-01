from __future__ import annotations

from clients.change_detection import run_change_detection
from state import AgentState


async def change_detection_node(state: AgentState) -> AgentState:
    # 变化检测和 3D 执行一样，节点层只表达“流程上有这一步”，
    # 具体怎么调服务、怎么处理响应，放到 client 层实现。
    return await run_change_detection(state)
