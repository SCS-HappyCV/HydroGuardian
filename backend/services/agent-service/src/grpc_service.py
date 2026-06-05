# agent-service 的 gRPC 服务入口。
# 这里专注处理请求生命周期编排；响应组装、下游客户端和 LangGraph 节点逻辑
# 都放在各自独立模块中。

from __future__ import annotations

import json

import grpc

from agent_graph import graph
from clients.case_file import build_persistence_failure_result, persist_case
from clients.file_assets import get_file_info
from generated import agent_pb2, agent_pb2_grpc
from responses import build_execute_task_reply
from scene_preprocess import (
    ScenePreprocessError,
    ScenePreprocessRequest,
    ScenePreprocessValidationError,
    preprocess_scene,
)
from state import AgentState, append_error


# 实现 proto 生成的 AgentRpcService 服务契约。
class AgentRpcServiceServicer(agent_pb2_grpc.AgentRpcServiceServicer):
    # 通过 LangGraph 流水线执行一条自然语言巡查任务。
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
                # case-service 失败不阻断主结果，但仍要保留 agent_result 快照，
                # 方便接口调用方回放本次执行链路。
                case_result = build_persistence_failure_result(final_state, exc)
                final_state["case_result"] = case_result

            # 统一把 final_state 转成对外 gRPC 响应，避免响应协议扩展时
            # 服务方法本身不断变胖。
            return build_execute_task_reply(
                request=request,
                state=final_state,
                case_result=case_result,
            )
        except Exception as exc:
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    # 预处理真实场景资产，生成 SceneTensorSample JSON 并自动注册 manifest。
    async def PreprocessScene(self, request, context):
        try:
            preprocess_request = ScenePreprocessRequest(
                scene_id=request.scene_id.strip(),
                sample_id=request.sample_id.strip(),
                image_file_id=request.image_file_id.strip(),
                point_cloud_file_id=request.point_cloud_file_id.strip(),
                pre_image_file_id=request.pre_image_file_id.strip(),
                post_image_file_id=request.post_image_file_id.strip(),
                preprocess_version=request.preprocess_version.strip(),
                image_size=int(request.image_size),
                max_points=int(request.max_points),
            )
            result = await preprocess_scene(preprocess_request)
            return agent_pb2.PreprocessSceneReply(
                scene_id=result.scene_id,
                sample_id=result.sample_id,
                scene_sample_file_id=result.scene_sample_file_id,
                image_file_id=result.image_file_id,
                point_cloud_file_id=result.point_cloud_file_id,
                pre_image_file_id=result.pre_image_file_id,
                post_image_file_id=result.post_image_file_id,
                preprocess_version=result.preprocess_version,
                manifest_registered=result.manifest_registered,
                checksum_sha256=result.checksum_sha256,
                scene_sample_file_name=result.scene_sample_file_name,
                status=result.status,
                quality_report_json=json.dumps(result.quality_report, ensure_ascii=False),
            )
        except ScenePreprocessValidationError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        except ScenePreprocessError as exc:
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))
        except Exception as exc:
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    # 通过 file-service 查询文件元数据并返回给网关调用方。
    async def QueryFile(self, request, context):
        try:
            file_result = await get_file_info(request.file_id)
            return agent_pb2.QueryFileReply(
                file_id=file_result.get("fileId", ""),
                file_name=file_result.get("fileName", ""),
                content_type=file_result.get("contentType", ""),
                size=int(file_result.get("size", 0)),
                download_url=file_result.get("downloadUrl", ""),
                object_key=file_result.get("objectKey", ""),
                file_type=file_result.get("fileType", ""),
                checksum_sha256=file_result.get("checksumSha256", ""),
            )
        except Exception as exc:
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))
