package com.hydro.casehub.dto;

public record UpdateCaseRequest(
        String title,
        String taskText,
        String sceneId,
        String status,
        String riskLevel,
        String assignee,
        String tags
) {
}

