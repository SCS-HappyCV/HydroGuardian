import {
  API_PATHS,
  type LoginRequest,
  type LoginResponseData,
  type RegisterRequest,
  type RegisterResponseData,
} from '@/lib/api-contracts'
import { httpClient } from '@/lib/http-client'

export const authApi = {
  login(data: LoginRequest) {
    return httpClient.post<LoginResponseData>(API_PATHS.auth.login, data, { withAuth: false })
  },
  register(data: RegisterRequest) {
    return httpClient.post<RegisterResponseData>(API_PATHS.auth.register, data, { withAuth: false })
  },
}
