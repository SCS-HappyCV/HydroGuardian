from __future__ import annotations

from clients.hydro_program3d import run_hydro_program3d
from state import AgentState


async def evidence_execution_node(state: AgentState) -> AgentState:
    # 这个节点本身很薄，只负责把图里的“执行 3D 证据服务”这一步
    # 显式挂出来。真正的 HTTP 调用细节都收在 client 层。
    return await run_hydro_program3d(state)
