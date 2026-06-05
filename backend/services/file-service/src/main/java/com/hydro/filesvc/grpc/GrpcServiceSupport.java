// gRPC 错误响应辅助类。
// 统一把业务错误转换成标准 gRPC Status。
package com.hydro.filesvc.grpc;

import io.grpc.Status;

public final class GrpcServiceSupport {

    // 工具类不需要实例化。
    private GrpcServiceSupport() {
    }

    // 构造参数错误。
    public static RuntimeException invalidArgument(String message) {
        return Status.INVALID_ARGUMENT.withDescription(message).asRuntimeException();
    }

    // 构造资源不存在错误。
    public static RuntimeException notFound(String message) {
        return Status.NOT_FOUND.withDescription(message).asRuntimeException();
    }

    // 构造内部错误，并保留原始异常。
    public static RuntimeException internal(String message, Throwable cause) {
        return Status.INTERNAL.withDescription(message).withCause(cause).asRuntimeException();
    }
}
