import type { SpatialLocationData } from '@/lib/spatial-location'

export interface WorkorderData {
  id: string
  title: string
  riskId: string
  taskId?: string
  caseId?: string
  assigneeUserId?: string
  reviewerUserId?: string
  ruleId: string
  templateId: string
  status: 'todo' | 'doing' | 'review' | 'closed'
  dueAt: string
  createdAt: string
  updatedAt: string
  summary: string
  aiRecommendation?: string
  priority?: 'urgent' | 'high' | 'normal'
  location?: SpatialLocationData
}

export type WorkorderFilterKey = keyof Pick<WorkorderData, 'status' | 'assigneeUserId' | 'reviewerUserId' | 'ruleId' | 'templateId'>
