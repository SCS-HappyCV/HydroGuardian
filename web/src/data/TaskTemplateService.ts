import type { TaskTemplateData, TaskTemplateFilterKey } from './TaskTemplateData'
import { getById as getZoneById } from './ZoneService'

export interface TaskTemplateVO extends TaskTemplateData {
  defaultZoneName?: string
}

export const taskTemplateDataList: TaskTemplateData[] = [
  {
    id: 'tpl-001',
    name: '夜间重点巡查',
    category: 'inspection',
    description: '适用于夜间高风险点位巡查，优先输出异常位置与建议动作。',
    defaultPriority: 'high',
    defaultZoneId: 'zone-01',
    isEnabled: true,
    createdAt: '2026-04-11T08:00:00Z',
    updatedAt: '2026-05-10T08:00:00Z'
  },
  {
    id: 'tpl-002',
    name: '雨后快速复核',
    category: 'review',
    description: '用于降雨后快速复核积水与排水设施状态。',
    defaultPriority: 'medium',
    defaultZoneId: 'zone-02',
    isEnabled: true,
    createdAt: '2026-04-12T08:00:00Z',
    updatedAt: '2026-05-11T08:00:00Z'
  },
  {
    id: 'tpl-003',
    name: '闸门应急核验',
    category: 'emergency',
    description: '用于闸门、泵站和边界设施的应急核验。',
    defaultPriority: 'high',
    defaultZoneId: 'zone-03',
    isEnabled: true,
    createdAt: '2026-04-13T08:00:00Z',
    updatedAt: '2026-05-12T08:00:00Z'
  },
  {
    id: 'tpl-004',
    name: '常规巡检模板',
    category: 'inspection',
    description: '适用于日常巡检任务，覆盖基础风险点排查。',
    defaultPriority: 'low',
    defaultZoneId: 'zone-04',
    isEnabled: true,
    createdAt: '2026-04-14T08:00:00Z',
    updatedAt: '2026-05-13T08:00:00Z'
  }
]

export function getAll(): TaskTemplateData[] {
  return taskTemplateDataList
}

export function getById(id: string): TaskTemplateData | undefined {
  return taskTemplateDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<TaskTemplateFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TaskTemplateData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = taskTemplateDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.name, item.description, item.category].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): TaskTemplateData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_task_template_data')
  return raw ? (JSON.parse(raw) as TaskTemplateData[]) : null
}

export function savePersisted(items: TaskTemplateData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_task_template_data', JSON.stringify(items))
}

export function getByIdVO(id: string): TaskTemplateVO | undefined {
  const item = getById(id)
  if (!item) return undefined
  return {
    ...item,
    defaultZoneName: getZoneById(item.defaultZoneId)?.name
  }
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<TaskTemplateFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TaskTemplateVO[] {
  return query(params).map((item) => getByIdVO(item.id)).filter((item): item is TaskTemplateVO => Boolean(item))
}
