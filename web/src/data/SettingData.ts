export interface SettingData {
  id: string
  key: string
  value: string
  category: 'basic' | 'data' | 'api' | 'security'
  isSensitive: boolean
  updatedAt: string
}

export type SettingFilterKey = keyof Pick<SettingData, 'category' | 'isSensitive'>
