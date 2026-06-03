// 提交智能体任务的 HTTP 请求体。
// 字段名沿用现有前端/API 的 JSON 契约。
package com.hydro.gateway.task;

import jakarta.validation.constraints.NotBlank;

public record ExecuteTaskRequest(
        @NotBlank(message = "taskText cannot be blank")
        String taskText,
        @NotBlank(message = "sceneId cannot be blank")
        String sceneId,
        Boolean debug
) {
    // debug 缺省时按 false 处理，保证旧客户端继续兼容。
    public boolean debugEnabled() {
        return Boolean.TRUE.equals(debug);
    }
}
