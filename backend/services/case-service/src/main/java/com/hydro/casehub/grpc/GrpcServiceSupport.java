package com.hydro.casehub.grpc;

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

    public static RuntimeException alreadyExists(String message) {
        return Status.ALREADY_EXISTS.withDescription(message).asRuntimeException();
    }

    public static RuntimeException unauthenticated(String message) {
        return Status.UNAUTHENTICATED.withDescription(message).asRuntimeException();
    }

    public static RuntimeException permissionDenied(String message) {
        return Status.PERMISSION_DENIED.withDescription(message).asRuntimeException();
    }

    public static RuntimeException internal(String message, Throwable cause) {
        return Status.INTERNAL.withDescription(message).withCause(cause).asRuntimeException();
    }
}
