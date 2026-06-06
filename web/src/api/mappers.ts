// API 映射工具：把后端响应转换成前端页面更容易消费的稳定结构。

import type {
  AgentErrorItem,
  AgentTraceItem,
  ExecuteTaskResponseData,
  TaskExecutionSnapshot,
  WorkOrderData,
} from '@/lib/api-contracts'

export type FrontendRiskLevel = 'high' | 'medium' | 'low' | 'review_required' | 'unknown'
export type FrontendWorkOrderStatus = 'todo' | 'doing' | 'review' | 'closed' | 'unknown'

// 尝试解析 trace/error 里的 dataJson 字符串，解析失败时返回原文。
export function parseEventData<T = unknown>(item: AgentTraceItem | AgentErrorItem): T | string | null {
  if (!item.dataJson) {
    return null
  }

  try {
    return JSON.parse(item.dataJson) as T
  } catch {
    return item.dataJson
  }
}

// 将后端风险等级归一化为前端现有风险页面使用的小写枚举。
export function normalizeRiskLevel(riskLevel: string): FrontendRiskLevel {
  const value = riskLevel.trim().toUpperCase()
  if (value === 'HIGH') return 'high'
  if (value === 'MEDIUM') return 'medium'
  if (value === 'LOW') return 'low'
  if (value === 'REVIEW_REQUIRED') return 'review_required'
  return 'unknown'
}

// 将后端工单状态归一化为当前前端工单页面使用的小写状态。
export function normalizeWorkOrderStatus(status: string): FrontendWorkOrderStatus {
  const value = status.trim().toUpperCase()
  if (value === 'TODO' || value === 'ASSIGNED') return 'todo'
  if (value === 'DOING' || value === 'IN_PROGRESS') return 'doing'
  if (value === 'REVIEW' || value === 'REVIEWED') return 'review'
  if (value === 'CLOSED') return 'closed'
  return 'unknown'
}

// 基于 ExecuteTask 响应构建本地可缓存的执行快照。
export function buildTaskExecutionSnapshot(
  data: ExecuteTaskResponseData,
  localTaskId = `task-${Date.now()}`,
): TaskExecutionSnapshot {
  return {
    localTaskId,
    taskText: data.task.taskText,
    sceneId: data.task.sceneId,
    targetType: data.parsed.targetType,
    parserSource: data.parsed.parserSource,
    evidenceStatus: data.execution.evidenceStatus,
    riskScore: data.risk.score,
    riskLevel: data.risk.riskLevel,
    reviewRequired: data.risk.reviewRequired,
    recommendationAction: data.recommendation.action,
    caseId: data.case.caseId,
    caseStatus: data.case.status,
    executionStatus: data.execution.status,
    traceTotal: data.execution.traceCount,
    errorCount: data.execution.errorCount,
    trace: data.trace ?? [],
    errors: data.errors ?? [],
    casePersistenceStatus: data.case.persistenceStatus,
    casePersistenceError: data.case.persistenceError,
    createdAt: new Date().toISOString(),
  }
}

// 将后端工单转换为前端列表可直接显示的轻量字段。
export function toWorkOrderListItem(workOrder: WorkOrderData) {
  return {
    id: workOrder.workOrderId,
    title: workOrder.title,
    summary: workOrder.summary,
    status: normalizeWorkOrderStatus(workOrder.status),
    assignee: workOrder.assignee,
    deadline: workOrder.deadline,
    riskLevel: normalizeRiskLevel(workOrder.riskLevel),
    updatedAt: workOrder.updatedAt,
  }
}
