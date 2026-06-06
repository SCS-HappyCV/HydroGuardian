// API 错误工具：把统一 HTTP 客户端抛出的错误转换成适合页面展示的文案和诊断信息。

import { ApiError } from '@/lib/http-client'

// 判断传入值是否为统一 API 错误对象。
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

// 获取页面可直接展示的错误文案。
export function getApiErrorMessage(error: unknown) {
  if (isApiError(error)) {
    return error.message || '请求失败，请稍后重试'
  }

  if (error instanceof Error) {
    return error.message
  }

  return '网络异常，请稍后重试'
}

// 获取调试用错误详情，适合放入 trace 面板或控制台。
export function getApiErrorDetail(error: unknown) {
  if (!isApiError(error)) {
    return {}
  }

  return {
    code: error.code,
    status: error.status,
    traceId: error.traceId,
    payload: error.payload,
  }
}
