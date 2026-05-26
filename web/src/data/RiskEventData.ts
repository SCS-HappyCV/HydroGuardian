export interface RiskEventData {
  id: string
  taskId: string
  zoneId: string
  ruleId: string
  templateId: string
  workorderId?: string
  title: string
  description: string
  level: 'high' | 'medium' | 'low' | 'review_required'
  score: number
  status: 'new' | 'review_required' | 'linked' | 'closed'
  evidenceSummary: string
  triggeredAt: string
  updatedAt: string
}

export type RiskEventFilterKey = keyof Pick<RiskEventData, 'taskId' | 'zoneId' | 'ruleId' | 'templateId' | 'level' | 'status'>
