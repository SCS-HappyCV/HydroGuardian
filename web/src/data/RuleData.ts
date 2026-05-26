export interface RuleData {
  id: string
  name: string
  version: string
  category: 'hydrology' | 'structure' | 'operation'
  conditionSummary: string
  isActive: boolean
  hitCount: number
  createdAt: string
  updatedAt: string
}

export type RuleFilterKey = keyof Pick<RuleData, 'category' | 'isActive'>
