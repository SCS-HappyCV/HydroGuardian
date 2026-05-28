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

  constructor(message: string, options: { code?: string; traceId?: string; status: number; payload?: ApiResponse }) {
    super(message)
    this.name = 'ApiError'
    this.code = options.code
    this.traceId = options.traceId
    this.status = options.status
    this.payload = options.payload
  }
}

function createTraceId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID().replace(/-/g, '')
  }

  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
}

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

function appendQuery(url: URL, query?: ApiQuery) {
  if (!query) return

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

function buildUrl(path: string, query?: ApiQuery) {
  const url = /^https?:\/\//i.test(path) ? new URL(path) : new URL(path, `${API_CONFIG.baseUrl}/`)
  appendQuery(url, query)
  return url.toString()
}

async function parsePayload<T>(response: Response): Promise<ApiResponse<T> | null> {
  const text = await response.text()
  if (!text) return null

  try {
    return JSON.parse(text) as ApiResponse<T>
  } catch {
    return null
  }
}

function getAuthHeader(withAuth: boolean) {
  if (!withAuth || typeof window === 'undefined') return null

  const { authToken } = useAuthState()
  return authToken.value ? `Bearer ${authToken.value}` : null
}

function bindAbortSignal(controller: AbortController, signal?: AbortSignal | null) {
  if (!signal) return

  if (signal.aborted) {
    controller.abort(signal.reason)
    return
  }

  signal.addEventListener('abort', () => controller.abort(signal.reason), { once: true })
}

export class HttpClient {
  request<T = unknown>(path: string, options: ApiRequestOptions = {}) {
    return request<T>(path, options)
  }

  get<T = unknown>(path: string, options?: Omit<ApiRequestOptions, 'body' | 'method'>) {
    return request<T>(path, { ...options, method: 'GET' })
  }

  post<T = unknown>(path: string, body?: RequestBody, options?: Omit<ApiRequestOptions, 'body' | 'method'>) {
    return request<T>(path, { ...options, body, method: 'POST' })
  }

  put<T = unknown>(path: string, body?: RequestBody, options?: Omit<ApiRequestOptions, 'body' | 'method'>) {
    return request<T>(path, { ...options, body, method: 'PUT' })
  }

  patch<T = unknown>(path: string, body?: RequestBody, options?: Omit<ApiRequestOptions, 'body' | 'method'>) {
    return request<T>(path, { ...options, body, method: 'PATCH' })
  }

  delete<T = unknown>(path: string, options?: Omit<ApiRequestOptions, 'body' | 'method'>) {
    return request<T>(path, { ...options, method: 'DELETE' })
  }
}

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
    globalThis.clearTimeout(timeout)
  }
}

export const httpClient = new HttpClient()
