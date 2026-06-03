# hydro-program3d HTTP 调用错误分类。
# 这里把 httpx 的异常、HTTP 状态码和协议错误统一成可追踪的结构化错误。

from __future__ import annotations

from dataclasses import dataclass

import httpx


# 表示一次 hydro-program3d 调用中的结构化失败。
@dataclass
class HydroProgram3DError(Exception):
    stage: str
    error_type: str
    message: str
    retryable: bool = False
    status_code: int | None = None
    duration_ms: int | None = None
    response_text: str = ""

    # 让异常字符串保持可读，方便老日志和 append_error 继续直接使用。
    def __str__(self) -> str:
        status = f" status={self.status_code}" if self.status_code is not None else ""
        return f"{self.stage} {self.error_type}{status}: {self.message}"

    # 转成 trace/errors/failure_evidence_pack 都能直接消费的字典。
    def to_trace_data(self) -> dict[str, object]:
        data: dict[str, object] = {
            "stage": self.stage,
            "error_type": self.error_type,
            "retryable": self.retryable,
            "message": self.message,
        }
        if self.status_code is not None:
            data["status_code"] = self.status_code
        if self.duration_ms is not None:
            data["duration_ms"] = self.duration_ms
        if self.response_text:
            data["response_text"] = self.response_text[:500]
        return data


# 根据 httpx 异常类型判断错误类别和是否可重试。
def classify_httpx_error(stage: str, exc: Exception, *, duration_ms: int | None = None) -> HydroProgram3DError:
    if isinstance(exc, httpx.TimeoutException):
        return HydroProgram3DError(
            stage=stage,
            error_type="timeout",
            message=str(exc),
            retryable=True,
            duration_ms=duration_ms,
        )
    if isinstance(exc, httpx.NetworkError):
        return HydroProgram3DError(
            stage=stage,
            error_type="connection_failed",
            message=str(exc),
            retryable=True,
            duration_ms=duration_ms,
        )
    return HydroProgram3DError(
        stage=stage,
        error_type="http_client_error",
        message=str(exc),
        retryable=False,
        duration_ms=duration_ms,
    )


# 将非 2xx HTTP 响应转换成结构化错误。
def http_status_error(stage: str, response: httpx.Response, *, duration_ms: int) -> HydroProgram3DError:
    status_code = response.status_code
    if status_code >= 500:
        error_type = "upstream_5xx"
        retryable = True
    elif status_code >= 400:
        error_type = "upstream_4xx"
        retryable = False
    else:
        error_type = "unexpected_status"
        retryable = False

    return HydroProgram3DError(
        stage=stage,
        error_type=error_type,
        message=response.text[:500],
        retryable=retryable,
        status_code=status_code,
        duration_ms=duration_ms,
        response_text=response.text,
    )
