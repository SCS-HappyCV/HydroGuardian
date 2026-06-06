// 认证 API 封装：集中处理登录、注册等账号相关 HTTP 请求。

import {
  API_PATHS,
  type LoginRequest,
  type LoginResponseData,
  type RegisterRequest,
  type RegisterResponseData,
} from '@/lib/api-contracts'
import { httpClient } from '@/lib/http-client'

export const authApi = {
  // 调用登录接口，登录阶段不携带已有鉴权头。
  login(data: LoginRequest) {
    return httpClient.post<LoginResponseData>(API_PATHS.auth.login, data, { withAuth: false })
  },

  // 调用注册接口，注册阶段不携带已有鉴权头。
  register(data: RegisterRequest) {
    return httpClient.post<RegisterResponseData>(API_PATHS.auth.register, data, { withAuth: false })
  },
}
