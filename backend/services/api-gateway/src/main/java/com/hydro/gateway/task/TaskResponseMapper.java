// 将 agent-service 的 gRPC 响应映射成前端期望的 HTTP 响应结构。
// 该 mapper 用来把协议细节从控制器中隔离出去。
package com.hydro.gateway.task;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hydro.grpc.agentv1.AgentErrorItem;
import com.hydro.grpc.agentv1.AgentTraceItem;
import com.hydro.grpc.agentv1.ExecuteTaskReply;

import java.util.LinkedHashMap;
import java.util.Map;

final class TaskResponseMapper {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final TypeReference<Object> JSON_TYPE = new TypeReference<>() {
    };

    // 工具类，不需要实例化。
    private TaskResponseMapper() {
    }

    // 将 ExecuteTaskReply 转成稳定的 HTTP 顶层响应分区。
    static Map<String, Object> toHttpData(ExecuteTaskReply reply, boolean debug) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("task", Map.of("taskText", reply.getTaskText(), "sceneId", reply.getSceneId()));
        data.put("parsed", Map.of(
                "targetType", reply.getTargetType(),
                "parserSource", reply.getParserSource()
        ));
        data.put("risk", Map.of(
                "score", reply.getRiskScore(),
                "riskLevel", reply.getRiskLevel(),
                "reviewRequired", reply.getReviewRequired()
        ));
        data.put("recommendation", Map.of("action", reply.getRecommendationAction()));
        data.put("workOrders", parseJson(reply.getWorkOrdersJson()));
        data.put("case", Map.of(
                "caseId", reply.getCaseId(),
                "status", reply.getCaseStatus(),
                "persistenceStatus", reply.getCasePersistenceStatus(),
                "persistenceError", reply.getCasePersistenceError()
        ));
        data.put("execution", Map.of(
                "status", reply.getExecutionStatus(),
                "evidenceStatus", reply.getEvidenceStatus(),
                "traceCount", reply.getTraceTotal(),
                "errorCount", reply.getErrorCount()
        ));

        // errors 体量小且便于排障，因此只要存在就返回。
        if (reply.getErrorCount() > 0) {
            data.put("errors", reply.getErrorsList().stream()
                    .map(TaskResponseMapper::toErrorMap)
                    .toList());
        }
        // trace 可能较长，仅在调用方显式开启 debug 时返回。
        if (debug) {
            data.put("trace", reply.getTraceList().stream()
                    .map(TaskResponseMapper::toTraceMap)
                    .toList());
        }
        return data;
    }

    // 将 agent-service 返回的工单 JSON 转成对象；解析失败时保留原始字符串。
    private static Object parseJson(String rawJson) {
        if (rawJson == null || rawJson.isBlank()) {
            return java.util.List.of();
        }
        try {
            return OBJECT_MAPPER.readValue(rawJson, JSON_TYPE);
        } catch (Exception ignored) {
            return rawJson;
        }
    }

    // 将 trace proto item 转成通用事件 map 结构。
    private static Map<String, Object> toTraceMap(AgentTraceItem item) {
        return compactEventMap(item.getStage(), item.getMessage(), item.getDataJson());
    }

    // 将 error proto item 转成通用事件 map 结构。
    private static Map<String, Object> toErrorMap(AgentErrorItem item) {
        return compactEventMap(item.getStage(), item.getMessage(), item.getDataJson());
    }

    // trace 和 errors 复用同一事件结构，简化前端渲染。
    private static Map<String, Object> compactEventMap(String stage, String message, String dataJson) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("stage", stage);
        item.put("message", message);
        if (dataJson != null && !dataJson.isBlank()) {
            item.put("dataJson", dataJson);
        }
        return item;
    }
}
