
import type { TaskStudioPresetData, TaskStudioPresetFilterKey } from './TaskStudioPresetData'

export interface TaskStudioPresetVO extends TaskStudioPresetData {}

export const taskStudioPresetDataList: TaskStudioPresetData[] = [
  {
    id: 'preset-001',
    name: '滨海泵站夜巡',
    description: '适用于滨海区域夜间巡检与风险预览。',
    defaultInputText: '请检查滨海泵站周边夜间异常水位波动并生成风险清单',
    defaultPriority: 'high',
    defaultZoneId: 'zone-01',
    defaultSampleId: 'sample-001',
    sortOrder: 1,
    isRecommended: true
  },
  {
    id: 'preset-002',
    name: '北岸排水渠复核',
    description: '用于排水渠淤积和低洼积水复核。',
    defaultInputText: '巡查北岸排水渠淤积与泵站连通情况，优先关注低洼区',
    defaultPriority: 'medium',
    defaultZoneId: 'zone-02',
    defaultSampleId: 'sample-003',
    sortOrder: 2,
    isRecommended: true
  },
  {
    id: 'preset-003',
    name: '南堤闸门核验',
    description: '用于闸门应急状态快速核验。',
    defaultInputText: '对南堤闸门的应急状态做一次快速复核，检查是否存在回流风险',
    defaultPriority: 'high',
    defaultZoneId: 'zone-03',
    defaultSampleId: 'sample-005',
    sortOrder: 3,
    isRecommended: true
  },
  {
    id: 'preset-004',
    name: '东湾雨后巡检',
    description: '用于降雨后排涝与积水检查。',
    defaultInputText: '根据最近降雨情况检查东湾片区内涝积水点和排水能力',
    defaultPriority: 'low',
    defaultZoneId: 'zone-04',
    defaultSampleId: 'sample-006',
    sortOrder: 4,
    isRecommended: false
  }
]

export function getAll(): TaskStudioPresetData[] {
  return taskStudioPresetDataList
}

export function getById(id: string): TaskStudioPresetData | undefined {
  return taskStudioPresetDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<TaskStudioPresetFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TaskStudioPresetData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = taskStudioPresetDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.name, item.description, item.defaultInputText].some((val) => val.toLowerCase().includes(keyword))
    const matchFilter = Object.entries(filter).every(([key, val]) => {
      if (val === undefined) return true
      const itemVal = (item as any)[key]
      return Array.isArray(val) ? val.includes(itemVal) : itemVal === val
    })
    return matchKeyword && matchFilter
  })
  const sortKey = params.sortKey
  if (!sortKey) return result
  return [...result].sort((a, b) => {
    const av = (a as any)[sortKey]
    const bv = (b as any)[sortKey]
    const direction = params.sortDirection === 'desc' ? -1 : 1
    if (av === bv) return 0
    return av > bv ? direction : -direction
  })
}

export function loadPersisted(): TaskStudioPresetData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_task_studio_preset_data')
  return raw ? (JSON.parse(raw) as TaskStudioPresetData[]) : null
}

export function savePersisted(items: TaskStudioPresetData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_task_studio_preset_data', JSON.stringify(items))
}

export function getByIdVO(id: string): TaskStudioPresetVO | undefined {
  return getById(id)
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<TaskStudioPresetFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TaskStudioPresetVO[] {
  return query(params)
}
      