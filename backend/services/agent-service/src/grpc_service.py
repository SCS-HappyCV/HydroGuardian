from __future__ import annotations

import grpc

from agent_graph import graph
from clients.case_file import get_file_info, persist_case
from generated import agent_pb2, agent_pb2_grpc
from state import AgentState, append_error


class AgentRpcServiceServicer(agent_pb2_grpc.AgentRpcServiceServicer):
    async def ExecuteTask(self, request, context):
        try:
            # request 只有比较薄的输入：task_text + scene_id。
            # 后面所有中间结果都靠这份 init_state 逐步补齐。
            # 所有节点都原地读写这份共享状态。初始化字段尽量在这里写全，
            # 这样后续接手的人能很快看清楚整条链路依赖了哪些上下文字段。
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
            # graph.ainvoke 会按照 agent_graph.py 里定义的顺序，依次执行各节点。
            final_state = await graph.ainvoke(init_state)

            try:
                # 持久化放在推理之后做。即使 case-service 暂时不可用，
                # 也不应该把已经生成的风险和建议结果一起吞掉。
                case_result = await persist_case(final_state)
                final_state["case_result"] = case_result
            except Exception as exc:
                append_error(final_state, "persist_case", str(exc))
                case_result = {}

            risk = final_state["risk_cards"][0] if final_state["risk_cards"] else {}
            recommendation = (
                final_state["recommendation_cards"][0] if final_state["recommendation_cards"] else {}
            )
            # 当前 gRPC 返回给上游的是“摘要结果”，不是完整证据链。
            # 如果后面前端或网关要展示完整 trace / evidence，需要扩 proto。
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
