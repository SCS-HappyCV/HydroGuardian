// 任务 API 封装：负责调用 agent-service 执行自然语言巡查任务。

import {
  API_PATHS,
  type ExecuteTaskRequestData,
  type ExecuteTaskResponseData,
} from '@/lib/api-contracts'
import { httpClient } from '@/lib/http-client'

// 执行一条自然语言巡查任务，并返回风险、case、trace 和错误摘要。
export function executeTask(data: ExecuteTaskRequestData) {
  return httpClient.post<ExecuteTaskResponseData>(API_PATHS.tasks.execute, data, {
    // 3D 服务执行可能较慢，任务接口单独给更长超时。
    timeoutMs: 120_000,
  })
}
