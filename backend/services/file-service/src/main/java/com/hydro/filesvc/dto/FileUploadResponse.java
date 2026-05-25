package com.hydro.filesvc.dto;

public record FileUploadResponse(
        String fileId,
        String fileName,
        String objectKey,
        Long size
) {
}

