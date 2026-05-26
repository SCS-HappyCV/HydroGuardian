export interface TaskTemplateData {
  id: string
  name: string
  category: 'inspection' | 'review' | 'emergency'
  description: string
  defaultPriority: 'low' | 'medium' | 'high'
  defaultZoneId: string
  isEnabled: boolean
  createdAt: string
  updatedAt: string
}

export type TaskTemplateFilterKey = keyof Pick<TaskTemplateData, 'category' | 'defaultPriority' | 'isEnabled' | 'defaultZoneId'>
