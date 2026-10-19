
import type { TaskStudioPresetData, TaskStudioPresetFilterKey } from './TaskStudioPresetData'

export interface TaskStudioPresetVO extends TaskStudioPresetData {}

export const taskStudioPresetDataList: TaskStudioPresetData[] = [
  {
    id: 'preset-001',
    name: '近水沟渠智能筛查',
    description: '识别近水细长沟渠，结合空间关系排除道路干扰。',
    defaultInputText: '找出靠近水线的细长沟渠，并排除道路，按风险高低排序',
    defaultPriority: 'high',
    defaultZoneId: 'zone-01',
    defaultSampleId: 'sample-001',
    sortOrder: 1,
    isRecommended: true
  },
  {
    id: 'preset-002',
    name: '陡坡裸地风险排查',
    description: '结合点云高程与坡度证据筛查临水陡坡裸地。',
    defaultInputText: '找出高于水线的陡坡裸地区域，并按坡度和临水距离排序',
    defaultPriority: 'medium',
    defaultZoneId: 'zone-02',
    defaultSampleId: 'sample-003',
    sortOrder: 2,
    isRecommended: true
  },
  {
    id: 'preset-003',
    name: '近水扰动变化检测',
    description: '对比前后时相影像，定位岸线附近新增扰动区域。',
    defaultInputText: '筛查近水扰动区域，结合前后影像变化按风险高低排序',
    defaultPriority: 'high',
    defaultZoneId: 'zone-03',
    defaultSampleId: 'sample-005',
    sortOrder: 3,
    isRecommended: true
  },
  {
    id: 'preset-004',
    name: '岸线多模态综合巡查',
    description: '综合使用正射影像、点云和变化检测完成岸线隐患巡查。',
    defaultInputText: '综合筛查岸线附近沟渠、陡坡裸地与新增扰动，输出证据和处置建议',
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
