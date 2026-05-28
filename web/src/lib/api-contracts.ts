export const DEFAULT_API_BASE_URL = 'http://localhost:8080'
export const API_VERSION_PREFIX = '/api/v1'
export const API_SUCCESS_CODE = '0'

export const API_ERROR_CODES = {
  badRequest: '40000',
  unauthorized: '40100',
  forbidden: '40300',
  notFound: '40400',
  conflict: '40900',
  validationFailed: '42200',
  internalError: '50000',
  upstreamUnavailable: '50200',
} as const

export const API_PATHS = {
  auth: {
    login: `${API_VERSION_PREFIX}/auth/login`,
    register: `${API_VERSION_PREFIX}/auth/register`,
    refresh: `${API_VERSION_PREFIX}/auth/refresh`,
    logout: `${API_VERSION_PREFIX}/auth/logout`,
    me: `${API_VERSION_PREFIX}/auth/me`,
    changePassword: `${API_VERSION_PREFIX}/auth/change-password`,
  },
} as const

export type ApiErrorCode = (typeof API_ERROR_CODES)[keyof typeof API_ERROR_CODES]
export type ApiCode = typeof API_SUCCESS_CODE | ApiErrorCode | (string & {})
export type ApiQueryValue = string | number | boolean | null | undefined
export type ApiQuery = Record<string, ApiQueryValue | ApiQueryValue[]>

export interface ApiResponse<T = unknown> {
  code: ApiCode
  message: string
  traceId: string
  data?: T
}

export interface ApiPageRequest {
  page?: number
  pageSize?: number
}

export interface ApiPageResponse<T> {
  records: T[]
  total: number
  page: number
  pageSize: number
}

export interface AuthUser {
  id: string
  name: string
  email: string
  role?: string
  department?: string
  avatarUrl?: string
}

export interface LoginRequest {
  email: string
  password: string
  rememberMe?: boolean
}

export interface LoginResponseData {
  token: string
  tokenType?: string
  expiresIn?: number
  user?: AuthUser
}

export interface RegisterRequest {
  name: string
  email: string
  password: string
  confirmPassword: string
  agreeTerms: boolean
}

export interface RegisterResponseData {
  userId?: string
  email?: string
  createdAt?: string
}

function normalizeBaseUrl(url: string) {
  return url.trim().replace(/\/+$/, '')
}

export const API_CONFIG = {
  baseUrl: normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL),
  timeoutMs: 15_000,
  successCode: API_SUCCESS_CODE,
} as const
