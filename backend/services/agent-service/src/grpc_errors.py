import grpc


def invalid_argument(context, message: str):
    return context.abort(grpc.StatusCode.INVALID_ARGUMENT, message)


def not_found(context, message: str):
    return context.abort(grpc.StatusCode.NOT_FOUND, message)


def internal(context, message: str):
    return context.abort(grpc.StatusCode.INTERNAL, message)
