import type { RuleData, RuleFilterKey } from './RuleData'

export interface RuleVO extends RuleData {}

export const ruleDataList: RuleData[] = [
  { id: 'rule-001', name: '连续水位上升触发', version: 'v1.3', category: 'hydrology', conditionSummary: '连续 3 次采样水位上升且超过阈值。', isActive: true, hitCount: 42, createdAt: '2026-03-01T00:00:00Z', updatedAt: '2026-05-15T00:00:00Z' },
  { id: 'rule-002', name: '低洼积水疑似变化', version: 'v2.0', category: 'hydrology', conditionSummary: '低洼区域出现面积扩大或边界模糊。', isActive: true, hitCount: 28, createdAt: '2026-03-05T00:00:00Z', updatedAt: '2026-05-14T00:00:00Z' },
  { id: 'rule-003', name: '淤积扩张检测', version: 'v1.1', category: 'operation', conditionSummary: '排水渠流速下降且淤积区域扩张。', isActive: true, hitCount: 17, createdAt: '2026-03-10T00:00:00Z', updatedAt: '2026-05-12T00:00:00Z' },
  { id: 'rule-004', name: '混接回流轻微异常', version: 'v1.0', category: 'structure', conditionSummary: '混接点回流迹象轻微但持续出现。', isActive: false, hitCount: 9, createdAt: '2026-03-15T00:00:00Z', updatedAt: '2026-05-01T00:00:00Z' }
]

export function getAll(): RuleData[] {
  return ruleDataList
}

export function getById(id: string): RuleData | undefined {
  return ruleDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<RuleFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): RuleData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = ruleDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.name, item.version, item.conditionSummary].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): RuleData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_rule_data')
  return raw ? (JSON.parse(raw) as RuleData[]) : null
}

export function savePersisted(items: RuleData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_rule_data', JSON.stringify(items))
}

export function getByIdVO(id: string): RuleVO | undefined {
  return getById(id)
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<RuleFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): RuleVO[] {
  return query(params)
}

export const RuleService = {
  getAll,
  getById,
  query,
  loadPersisted,
  savePersisted,
  getByIdVO,
  queryVO
}
