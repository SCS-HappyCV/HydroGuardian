import type { TemplateData, TemplateFilterKey } from './TemplateData'

export interface TemplateVO extends TemplateData {}

export const templateDataList: TemplateData[] = [
  { id: 'tpl-a01', name: '高风险现场核查模板', type: 'dispatch', applicableRiskLevels: ['high'], content: '携带风险定位和多模态证据派发现场核查，要求 2 小时内反馈。', callCount: 18, isEnabled: true, createdAt: '2026-03-02T00:00:00Z', updatedAt: '2026-05-15T00:00:00Z' },
  { id: 'tpl-a02', name: '低置信证据复核模板', type: 'review', applicableRiskLevels: ['medium', 'review_required'], content: '补充现场影像或高程证据，并在 24 小时内完成复核。', callCount: 22, isEnabled: true, createdAt: '2026-03-04T00:00:00Z', updatedAt: '2026-05-14T00:00:00Z' },
  { id: 'tpl-a03', name: '低风险观察模板', type: 'dispatch', applicableRiskLevels: ['low'], content: '持续观察并记录变化趋势，无需立即处置。', callCount: 11, isEnabled: true, createdAt: '2026-03-08T00:00:00Z', updatedAt: '2026-05-10T00:00:00Z' },
  { id: 'tpl-a04', name: '闭环复盘模板', type: 'review', applicableRiskLevels: ['high', 'medium', 'low'], content: '整理处理过程、复核意见与后续建议。', callCount: 7, isEnabled: false, createdAt: '2026-03-12T00:00:00Z', updatedAt: '2026-05-01T00:00:00Z' }
]

export function getAll(): TemplateData[] {
  return templateDataList
}

export function getById(id: string): TemplateData | undefined {
  return templateDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<TemplateFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TemplateData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = templateDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.name, item.content].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): TemplateData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_template_data')
  return raw ? (JSON.parse(raw) as TemplateData[]) : null
}

export function savePersisted(items: TemplateData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_template_data', JSON.stringify(items))
}

export function getByIdVO(id: string): TemplateVO | undefined {
  return getById(id)
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<TemplateFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TemplateVO[] {
  return query(params)
}

export const TemplateService = {
  getAll,
  getById,
  query,
  loadPersisted,
  savePersisted,
  getByIdVO,
  queryVO,
}
