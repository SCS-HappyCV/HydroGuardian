package com.hydro.casehub.dto;

import java.time.LocalDateTime;

public record CaseResponse(
        String caseId,
        String title,
        String taskText,
        String sceneId,
        String status,
        String riskLevel,
        String assignee,
        String tags,
        LocalDateTime createdAt
) {
}

