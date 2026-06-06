// 更新工单状态的 HTTP 请求体。
// 前端通过该请求推进 TODO -> ASSIGNED -> IN_PROGRESS -> REVIEWED -> CLOSED 状态流。
package com.hydro.gateway.workorder;

import jakarta.validation.constraints.NotBlank;

public record UpdateWorkOrderStatusRequest(
        // 目标状态，支持 TODO、ASSIGNED、IN_PROGRESS、REVIEWED、CLOSED。
        @NotBlank(message = "status cannot be blank")
        String status,
        // 可选负责人；为空时 case-service 保持原负责人不变。
        String assignee,
        // 可选关闭或复核说明；为空时保持原说明不变。
        String closureNote
) {
}
