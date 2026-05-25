package com.hydro.filesvc.grpc;

import io.grpc.Status;

public final class GrpcServiceSupport {

    private GrpcServiceSupport() {
    }

    public static RuntimeException invalidArgument(String message) {
        return Status.INVALID_ARGUMENT.withDescription(message).asRuntimeException();
    }

    public static RuntimeException notFound(String message) {
        return Status.NOT_FOUND.withDescription(message).asRuntimeException();
    }

    public static RuntimeException internal(String message, Throwable cause) {
        return Status.INTERNAL.withDescription(message).withCause(cause).asRuntimeException();
    }
}

