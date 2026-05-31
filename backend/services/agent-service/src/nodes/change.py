from __future__ import annotations

from clients.change_detection import run_change_detection
from state import AgentState


async def change_detection_node(state: AgentState) -> AgentState:
    return await run_change_detection(state)
