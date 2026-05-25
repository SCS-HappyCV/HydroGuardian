package com.hydro.gateway.common;

public enum ErrorCode {
    SUCCESS("0", "OK", 200),
    BAD_REQUEST("40000", "Bad Request", 400),
    NOT_FOUND("40400", "Not Found", 404),
    UPSTREAM_ERROR("50200", "Upstream Service Error", 502),
    INTERNAL_ERROR("50000", "Internal Server Error", 500);

    private final String code;
    private final String message;
    private final int httpStatus;

    ErrorCode(String code, String message, int httpStatus) {
        this.code = code;
        this.message = message;
        this.httpStatus = httpStatus;
    }

    public String getCode() {
        return code;
    }

    public String getMessage() {
        return message;
    }

    public int getHttpStatus() {
        return httpStatus;
    }
}
