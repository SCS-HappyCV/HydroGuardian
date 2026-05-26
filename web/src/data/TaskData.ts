export interface TaskData {
  id: string
  name: string
  inputText: string
  templateId: string
  zoneId: string
  sampleId?: string
  priority: 'low' | 'medium' | 'high'
  status: 'queued' | 'running' | 'success' | 'failed'
  progress: number
  createdAt: string
  startedAt?: string
  finishedAt?: string
  createdByUserId: string
  updatedAt: string
}

export type TaskFilterKey = keyof Pick<TaskData, 'zoneId' | 'templateId' | 'priority' | 'status' | 'createdByUserId'>
