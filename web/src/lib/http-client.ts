// 统一 HTTP 客户端：负责 API URL 拼接、JSON/FormData 请求、鉴权头、超时和错误封装。

import {
  API_CONFIG,
  API_SUCCESS_CODE,
  type ApiQuery,
  type ApiQueryValue,
  type ApiResponse,
} from '@/lib/api-contracts'
import { useAuthState } from '@/lib/auth'

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
type RequestBody = BodyInit | object | null | undefined

export interface ApiRequestOptions extends Omit<RequestInit, 'body' | 'method'> {
  body?: RequestBody
  method?: HttpMethod
  query?: ApiQuery
  timeoutMs?: number
  withAuth?: boolean
}

export class ApiError extends Error {
  code?: string
  traceId?: string
  status: number
  payload?: ApiResponse

  // 构造统一 API 错误，保留 HTTP 状态、业务 code、traceId 和原始响应。
  constructor(message: string, options: { code?: string; traceId?: string; status: number; payload?: ApiResponse }) {
    super(message)
    this.name = 'ApiError'
    this.code = options.code
    this.traceId = options.traceId
    this.status = options.status
    this.payload = options.payload
  }
}

// 创建前端请求 traceId；浏览器不支持 randomUUID 时使用时间戳兜底。
function createTraceId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID().replace(/-/g, '')
  }

  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
}

// 判断请求体是否应该按 JSON 序列化，FormData/Blob/流等二进制体保持原样。
function isJsonBody(body: RequestBody): body is object {
  if (!body || typeof body !== 'object') return false
  if (typeof FormData !== 'undefined' && body instanceof FormData) return false
  if (typeof URLSearchParams !== 'undefined' && body instanceof URLSearchParams) return false
  if (typeof Blob !== 'undefined' && body instanceof Blob) return false
  if (typeof ArrayBuffer !== 'undefined' && body instanceof ArrayBuffer) return false
  if (typeof ArrayBuffer !== 'undefined' && ArrayBuffer.isView(body)) return false
  if (typeof ReadableStream !== 'undefined' && body instanceof ReadableStream) return false
  return true
}

// 将 query 对象追加到 URL，自动跳过空值。
function appendQuery(url: URL, query?: ApiQuery) {
  if (!query) return

  // 追加单个 query 参数，保留 boolean/number 的字符串化结果。
  const append = (key: string, value: ApiQueryValue) => {
    if (value === undefined || value === null || value === '') return
    url.searchParams.append(key, String(value))
  }

  Object.entries(query).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      value.forEach((item) => append(key, item))
      return
    }

    append(key, value)
  })
}

// 构造完整请求 URL，支持传入绝对地址或相对 API path。
function buildUrl(path: string, query?: ApiQuery) {
  const url = /^https?:\/\//i.test(path) ? new URL(path) : new URL(path, `${API_CONFIG.baseUrl}/`)
  appendQuery(url, query)
  return url.toString()
}

// 解析后端统一响应外壳；非 JSON 响应返回 null 交给上层错误处理。
async function parsePayload<T>(response: Response): Promise<ApiResponse<T> | null> {
  const text = await response.text()
  if (!text) return null

  try {
    return JSON.parse(text) as ApiResponse<T>
  } catch {
    return null
  }
}

// 根据调用配置读取鉴权头；SSR 阶段不读取 localStorage 状态。
function getAuthHeader(withAuth: boolean) {
  if (!withAuth || typeof window === 'undefined') return null

  const { authToken } = useAuthState()
  return authToken.value ? `Bearer ${authToken.value}` : null
}

// 将外部传入的 AbortSignal 绑定到本次请求的 AbortController。
function bindAbortSignal(controller: AbortController, signal?: AbortSignal | null) {
  if (!signal) return

  if (signal.aborted) {
    controller.abort(signal.reason)
    return
  }

  signal.addEventListener('abort', () => controller.abort(signal.reason), { once: true })
}

export class HttpClient {
  // 发起通用请求，适合需要自定义 method/query/header 的场景。
  request<T = unknown>(path: string, options: ApiRequestOptions = {}) {
    return request<T>(path, options)
  }

  // 发起 GET 请求。
  get<T = unknown>(path: string, options?: Omit<ApiRequestOptions, 'body' | 'method'>) {
    return request<T>(path, { ...options, method: 'GET' })
  }

  // 发起 POST 请求。
  post<T = unknown>(path: string, body?: RequestBody, options?: Omit<ApiRequestOptions, 'body' | 'method'>) {
    return request<T>(path, { ...options, body, method: 'POST' })
  }

  // 发起 PUT 请求。
  put<T = unknown>(path: string, body?: RequestBody, options?: Omit<ApiRequestOptions, 'body' | 'method'>) {
    return request<T>(path, { ...options, body, method: 'PUT' })
  }

  // 发起 PATCH 请求。
  patch<T = unknown>(path: string, body?: RequestBody, options?: Omit<ApiRequestOptions, 'body' | 'method'>) {
    return request<T>(path, { ...options, body, method: 'PATCH' })
  }

  // 发起 DELETE 请求。
  delete<T = unknown>(path: string, options?: Omit<ApiRequestOptions, 'body' | 'method'>) {
    return request<T>(path, { ...options, method: 'DELETE' })
  }
}

// 统一请求实现：处理请求体、traceId、鉴权、超时、响应外壳和错误封装。
export async function request<T = unknown>(path: string, options: ApiRequestOptions = {}) {
  const {
    body,
    headers,
    method = body === undefined ? 'GET' : 'POST',
    query,
    timeoutMs = API_CONFIG.timeoutMs,
    withAuth = true,
    ...rest
  } = options

  const controller = new AbortController()
  bindAbortSignal(controller, rest.signal)

  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs)
  const requestHeaders = new Headers(headers)
  const traceId = requestHeaders.get('X-Trace-Id') || createTraceId()
  const authHeader = getAuthHeader(withAuth)
  let requestBody: BodyInit | undefined

  // 所有请求都带 traceId，方便和后端日志串起来。
  requestHeaders.set('Accept', 'application/json')
  requestHeaders.set('X-Trace-Id', traceId)

  if (authHeader) {
    requestHeaders.set('Authorization', authHeader)
  }

  if (isJsonBody(body)) {
    if (!requestHeaders.has('Content-Type')) {
      requestHeaders.set('Content-Type', 'application/json')
    }
    requestBody = JSON.stringify(body)
  } else {
    requestBody = body ?? undefined
  }

  try {
    // fetch 只负责底层传输，成功/失败以统一响应外壳为准。
    const response = await fetch(buildUrl(path, query), {
      ...rest,
      body: requestBody,
      headers: requestHeaders,
      method,
      signal: controller.signal,
    })

    const payload = await parsePayload<T>(response)
    const isSuccess = response.ok && payload?.code === API_SUCCESS_CODE

    if (!isSuccess) {
      // HTTP 状态或业务 code 任一失败，都统一抛出 ApiError。
      throw new ApiError(payload?.message || '请求失败，请稍后重试', {
        code: payload?.code,
        traceId: payload?.traceId || response.headers.get('X-Trace-Id') || traceId,
        status: response.status,
        payload: payload ?? undefined,
      })
    }

    return payload as ApiResponse<T>
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }

    // AbortError 在这里统一转成用户可读的超时错误。
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('请求超时，请稍后重试', {
        status: 0,
        traceId,
      })
    }

    throw new ApiError(error instanceof Error ? error.message : '网络异常，请稍后重试', {
      status: 0,
      traceId,
    })
  } finally {
    // 请求结束后清理超时计时器，避免页面长时间运行时积累无效 timer。
    globalThis.clearTimeout(timeout)
  }
}

export const httpClient = new HttpClient()
