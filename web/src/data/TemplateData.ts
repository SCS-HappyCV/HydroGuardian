export interface TemplateData {
  id: string
  name: string
  type: 'dispatch' | 'review'
  applicableRiskLevels: ('high' | 'medium' | 'low' | 'review_required')[]
  content: string
  callCount: number
  isEnabled: boolean
  createdAt: string
  updatedAt: string
}

export type TemplateFilterKey = keyof Pick<TemplateData, 'type' | 'isEnabled'>
