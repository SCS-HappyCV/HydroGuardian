
export interface TaskStudioPresetData {
  id: string
  name: string
  description: string
  defaultInputText: string
  defaultPriority: 'low' | 'medium' | 'high'
  defaultZoneId: string
  defaultSampleId?: string
  sortOrder: number
  isRecommended: boolean
}

export type TaskStudioPresetFilterKey = keyof Pick<TaskStudioPresetData, 'defaultPriority' | 'defaultZoneId' | 'isRecommended'>
      