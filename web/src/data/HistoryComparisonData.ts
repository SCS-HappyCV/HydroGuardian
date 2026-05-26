
export interface HistoryComparisonData {
  id: string
  leftTaskId: string
  rightTaskId: string
  addedRiskIds: string[]
  removedRiskIds: string[]
  changedRiskIds: string[]
  summary: string
  createdAt: string
}

export type HistoryComparisonFilterKey = keyof Pick<HistoryComparisonData, 'leftTaskId' | 'rightTaskId'>
      