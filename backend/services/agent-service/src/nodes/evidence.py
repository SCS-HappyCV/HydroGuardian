from __future__ import annotations

from clients.hydro_program3d import run_hydro_program3d
from state import AgentState


async def evidence_execution_node(state: AgentState) -> AgentState:
    return await run_hydro_program3d(state)
