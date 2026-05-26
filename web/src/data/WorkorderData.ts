export interface WorkorderData {
  id: string
  title: string
  riskId: string
  assigneeUserId?: string
  reviewerUserId?: string
  ruleId: string
  templateId: string
  status: 'todo' | 'doing' | 'review' | 'closed'
  dueAt: string
  createdAt: string
  updatedAt: string
  summary: string
}

export type WorkorderFilterKey = keyof Pick<WorkorderData, 'status' | 'assigneeUserId' | 'reviewerUserId' | 'ruleId' | 'templateId'>
