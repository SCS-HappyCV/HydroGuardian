package com.hydro.casehub.dto;

import jakarta.validation.constraints.NotBlank;

public record CreateCaseRequest(
        @NotBlank(message = "title cannot be blank")
        String title,
        @NotBlank(message = "taskText cannot be blank")
        String taskText,
        @NotBlank(message = "sceneId cannot be blank")
        String sceneId,
        String riskLevel,
        String assignee,
        String tags
) {
}

