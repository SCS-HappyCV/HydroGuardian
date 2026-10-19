// case 智能体快照响应映射器。
// 将 case-service 的 CaseReply 转成前端可直接消费的 agent-result JSON 数据。
package com.hydro.gateway.casequery;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.hydro.gateway.common.ErrorCode;
import com.hydro.gateway.common.ServiceException;
import com.hydro.grpc.casev1.CaseReply;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class CaseAgentResultResponseMapper {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final TypeReference<Object> JSON_TYPE = new TypeReference<>() {
    };

    // 工具类不需要实例化。
    private CaseAgentResultResponseMapper() {
    }

    // 转换完整 case agent-result 响应；快照为空时明确返回 404，避免前端误展示空结果。
    static Map<String, Object> toHttpData(CaseReply reply) {
        String rawSnapshot = reply.getAgentResultJson();
        if (rawSnapshot == null || rawSnapshot.isBlank()) {
            throw new ServiceException(ErrorCode.NOT_FOUND, "agent result not found for case: " + reply.getCaseId());
        }

        Object parsedSnapshot = parseRequiredJson(rawSnapshot, "agent_result_json is not valid JSON");
        Map<String, Object> snapshot = ensureObject(parsedSnapshot, "agent_result_json root must be an object");
        Map<String, Object> data = asObjectMap(camelizeValue(snapshot));

        // 顶层补充 case-service 主表信息；不覆盖 agent 快照里的执行状态字段。
        data.putIfAbsent("caseId", reply.getCaseId());
        data.putIfAbsent("caseStatus", reply.getStatus());
        data.putIfAbsent("caseRiskLevel", reply.getRiskLevel());
        data.putIfAbsent("caseTitle", reply.getTitle());
        data.putIfAbsent("caseAssignee", reply.getAssignee());
        data.putIfAbsent("caseCreatedAt", reply.getCreatedAt());
        data.put("case", buildCaseSummary(reply));
        return data;
    }

    // 构建 case 主表摘要，供前端在工作台顶部展示业务状态。
    private static Map<String, Object> buildCaseSummary(CaseReply reply) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("caseId", reply.getCaseId());
        data.put("title", reply.getTitle());
        data.put("taskText", reply.getTaskText());
        data.put("sceneId", reply.getSceneId());
        data.put("status", reply.getStatus());
        data.put("riskLevel", reply.getRiskLevel());
        data.put("assignee", reply.getAssignee());
        data.put("tags", parseOptionalJson(reply.getTags()));
        data.put("createdAt", reply.getCreatedAt());
        return data;
    }

    // 解析必须存在的 JSON 字符串；数据库中的非法快照视为上游数据错误。
    private static Object parseRequiredJson(String rawJson, String errorMessage) {
        try {
            return OBJECT_MAPPER.readValue(rawJson, JSON_TYPE);
        } catch (Exception exc) {
            throw new ServiceException(ErrorCode.UPSTREAM_ERROR, errorMessage);
        }
    }

    // 解析可选 JSON 字符串；解析失败时保留原始字符串，避免辅助字段拖垮主响应。
    private static Object parseOptionalJson(String rawJson) {
        if (rawJson == null || rawJson.isBlank()) {
            return List.of();
        }
        try {
            return camelizeValue(OBJECT_MAPPER.readValue(rawJson, JSON_TYPE));
        } catch (Exception ignored) {
            return rawJson;
        }
    }

    // 校验 JSON 根节点必须是对象。
    private static Map<String, Object> ensureObject(Object value, String errorMessage) {
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> result = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                result.put(String.valueOf(entry.getKey()), entry.getValue());
            }
            return result;
        }
        throw new ServiceException(ErrorCode.UPSTREAM_ERROR, errorMessage);
    }

    // 把递归转换后的值收窄成对象类型。
    private static Map<String, Object> asObjectMap(Object value) {
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> result = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                result.put(String.valueOf(entry.getKey()), entry.getValue());
            }
            return result;
        }
        return new LinkedHashMap<>();
    }

    // 递归转换 Map/List 中的 snake_case key，保持前端 API 字段风格一致。
    private static Object camelizeValue(Object value) {
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> result = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                result.put(toCamelCase(String.valueOf(entry.getKey())), camelizeValue(entry.getValue()));
            }
            return result;
        }
        if (value instanceof List<?> list) {
            List<Object> result = new ArrayList<>(list.size());
            for (Object item : list) {
                result.add(camelizeValue(item));
            }
            return result;
        }
        return value;
    }

    // 将 snake_case 字段名转换为 lowerCamelCase。
    private static String toCamelCase(String value) {
        StringBuilder result = new StringBuilder(value.length());
        boolean upperNext = false;
        for (int index = 0; index < value.length(); index++) {
            char current = value.charAt(index);
            if (current == '_') {
                upperNext = result.length() > 0;
                continue;
            }
            if (upperNext) {
                result.append(Character.toUpperCase(current));
                upperNext = false;
            } else {
                result.append(current);
            }
        }
        return result.toString();
    }
}
