package com.hydro.gateway.common;

import com.hydro.gateway.dto.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import io.grpc.StatusRuntimeException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.RestClientException;

import java.util.UUID;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiResponse<Void>> handleValidation(MethodArgumentNotValidException ex, HttpServletRequest request) {
        String message = ex.getBindingResult().getFieldErrors().stream()
                .findFirst()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .orElse("validation failed");
        return build(ErrorCode.BAD_REQUEST, message, request);
    }

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<ApiResponse<Void>> handleConstraint(ConstraintViolationException ex, HttpServletRequest request) {
        return build(ErrorCode.BAD_REQUEST, ex.getMessage(), request);
    }

    @ExceptionHandler(RestClientException.class)
    public ResponseEntity<ApiResponse<Void>> handleUpstream(RestClientException ex, HttpServletRequest request) {
        return build(ErrorCode.UPSTREAM_ERROR, ex.getMessage(), request);
    }

    @ExceptionHandler(StatusRuntimeException.class)
    public ResponseEntity<ApiResponse<Void>> handleGrpc(StatusRuntimeException ex, HttpServletRequest request) {
        ErrorCode code = GrpcErrorMapper.toErrorCode(ex.getStatus().getCode());
        return build(code, ex.getStatus().getDescription(), request);
    }

    @ExceptionHandler(ServiceException.class)
    public ResponseEntity<ApiResponse<Void>> handleService(ServiceException ex, HttpServletRequest request) {
        return build(ex.getErrorCode(), ex.getMessage(), request);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleAny(Exception ex, HttpServletRequest request) {
        return build(ErrorCode.INTERNAL_ERROR, ex.getMessage(), request);
    }

    private ResponseEntity<ApiResponse<Void>> build(ErrorCode errorCode, String message, HttpServletRequest request) {
        String traceId = getOrCreateTraceId(request);
        return ResponseEntity.status(errorCode.getHttpStatus())
                .body(ApiResponse.error(errorCode.getCode(), message, traceId));
    }

    private String getOrCreateTraceId(HttpServletRequest request) {
        String traceId = request.getHeader("X-Trace-Id");
        if (traceId == null || traceId.isBlank()) {
            traceId = UUID.randomUUID().toString().replace("-", "");
        }
        request.setAttribute("traceId", traceId);
        return traceId;
    }
}
