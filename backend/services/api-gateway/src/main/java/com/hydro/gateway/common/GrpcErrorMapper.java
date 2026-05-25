package com.hydro.gateway.common;

import io.grpc.Status;

public final class GrpcErrorMapper {

    private GrpcErrorMapper() {
    }

    public static ErrorCode toErrorCode(Status.Code code) {
        return switch (code) {
            case INVALID_ARGUMENT, FAILED_PRECONDITION -> ErrorCode.BAD_REQUEST;
            case NOT_FOUND -> ErrorCode.NOT_FOUND;
            case UNAVAILABLE, DEADLINE_EXCEEDED -> ErrorCode.UPSTREAM_ERROR;
            default -> ErrorCode.INTERNAL_ERROR;
        };
    }
}
