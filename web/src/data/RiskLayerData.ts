export interface RiskLayerData {
  id: string
  name: string
  iconName: string
  isEnabled: boolean
  sortOrder: number
}

export type RiskLayerFilterKey = keyof Pick<RiskLayerData, 'isEnabled'>
