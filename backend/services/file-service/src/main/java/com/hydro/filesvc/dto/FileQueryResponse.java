package com.hydro.filesvc.dto;

public record FileQueryResponse(
        String fileId,
        String fileName,
        String contentType,
        Long size,
        String downloadUrl
) {
}

