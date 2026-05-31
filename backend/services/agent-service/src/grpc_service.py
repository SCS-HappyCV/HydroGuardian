from __future__ import annotations

import grpc

from agent_graph import graph
from clients.case_file import get_file_info, persist_case
from generated import agent_pb2, agent_pb2_grpc
from state import AgentState, append_error


class AgentRpcServiceServicer(agent_pb2_grpc.AgentRpcServiceServicer):
    async def ExecuteTask(self, request, context):
        try:
            init_state: AgentState = {
                "case_id": "",
                "task_id": "",
                "task_text": request.task_text,
                "scene_id": request.scene_id,
                "sample_id": request.scene_id or "demo-001",
                "task_intent": {},
                "program_bundle": {},
                "selected_program": {},
                "scene_tensor_sample": {},
                "raw_executor_output": {},
                "evidence_pack": {},
                "change_pack": {},
                "risk_cards": [],
                "recommendation_cards": [],
                "work_orders": [],
                "case_result": {},
                "status": "INIT",
                "errors": [],
                "trace": [],
            }
            final_state = await graph.ainvoke(init_state)

            try:
                case_result = await persist_case(final_state)
                final_state["case_result"] = case_result
            except Exception as exc:
                append_error(final_state, "persist_case", str(exc))
                case_result = {}

            risk = final_state["risk_cards"][0] if final_state["risk_cards"] else {}
            recommendation = (
                final_state["recommendation_cards"][0] if final_state["recommendation_cards"] else {}
            )
            return agent_pb2.ExecuteTaskReply(
                task_text=request.task_text,
                scene_id=request.scene_id,
                target_type=str(final_state["task_intent"].get("target", "")),
                risk_score=float(risk.get("risk_score", 0.0)),
                risk_level=str(risk.get("risk_level", "")),
                recommendation_action=str(recommendation.get("recommended_action", "")),
                case_id=case_result.get("caseId", ""),
                case_status=case_result.get("status", ""),
            )
        except Exception as exc:
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def QueryFile(self, request, context):
        try:
            file_result = await get_file_info(request.file_id)
            return agent_pb2.QueryFileReply(
                file_id=file_result.get("fileId", ""),
                file_name=file_result.get("fileName", ""),
                content_type=file_result.get("contentType", ""),
                size=int(file_result.get("size", 0)),
                download_url=file_result.get("downloadUrl", ""),
            )
        except Exception as exc:
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))
