// 工单响应映射器。
// 将 case-service 的 WorkOrderReply 转换成前端稳定使用的 HTTP JSON 字段。
package com.hydro.gateway.workorder;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hydro.grpc.casev1.WorkOrderReply;

import java.util.LinkedHashMap;
import java.util.Map;

final class WorkOrderResponseMapper {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final TypeReference<Object> JSON_TYPE = new TypeReference<>() {
    };

    // 工具类不需要实例化。
    private WorkOrderResponseMapper() {
    }

    // 转换单个工单响应，并保持字段顺序便于前端联调。
    static Map<String, Object> toHttpData(WorkOrderReply reply) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("workOrderId", reply.getWorkOrderId());
        data.put("caseId", reply.getCaseId());
        data.put("riskCardId", reply.getRiskCardId());
        data.put("riskType", reply.getRiskType());
        data.put("riskLevel", reply.getRiskLevel());
        data.put("title", reply.getTitle());
        data.put("summary", reply.getSummary());
        data.put("recommendedAction", reply.getRecommendedAction());
        data.put("status", reply.getStatus());
        data.put("assignee", reply.getAssignee());
        data.put("deadline", reply.getDeadline());
        data.put("closureNote", reply.getClosureNote());
        data.put("evidenceSummary", parseJson(reply.getEvidenceSummaryJson()));
        data.put("schemaVersion", reply.getSchemaVersion());
        data.put("createdAt", reply.getCreatedAt());
        data.put("updatedAt", reply.getUpdatedAt());
        return data;
    }

    // 解析证据摘要 JSON；解析失败时保留原始字符串，避免响应整体失败。
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
}
