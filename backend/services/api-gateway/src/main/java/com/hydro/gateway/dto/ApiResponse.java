package com.hydro.gateway.dto;

public record ApiResponse<T>(
        String code,
        String message,
        T data,
        String traceId
) {
    public static <T> ApiResponse<T> success(T data, String traceId) {
        return new ApiResponse<>("0", "OK", data, traceId);
    }

    public static <T> ApiResponse<T> error(String code, String message, String traceId) {
        return new ApiResponse<>(code, message, null, traceId);
    }
}

