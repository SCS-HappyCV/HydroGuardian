export interface TaskResultData {
  id: string
  taskId: string
  summary: string
  highRiskCount: number
  mediumRiskCount: number
  lowRiskCount: number
  reviewRequiredCount: number
  createdAt: string
}

export type TaskResultFilterKey = keyof Pick<TaskResultData, 'taskId'>
