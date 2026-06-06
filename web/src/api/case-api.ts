// Case API 封装：负责 case 关联资源查询，尤其是工单和未来的智能体快照。

import {
  API_PATHS,
  type AgentResultSnapshotData,
  type ListCaseWorkOrdersResponseData,
} from '@/lib/api-contracts'
import { httpClient } from '@/lib/http-client'

// 查询指定 case 下的所有工单。
export function getCaseWorkOrders(caseId: string) {
  return httpClient.get<ListCaseWorkOrdersResponseData>(API_PATHS.cases.workOrders(caseId))
}

// 查询完整智能体执行快照；当前后端如未实现，调用方应捕获 404 并使用摘要结果兜底。
export function getCaseAgentResult(caseId: string) {
  return httpClient.get<AgentResultSnapshotData>(API_PATHS.cases.agentResult(caseId))
}
