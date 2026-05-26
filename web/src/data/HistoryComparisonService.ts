
import type { HistoryComparisonData, HistoryComparisonFilterKey } from './HistoryComparisonData'

export interface HistoryComparisonVO extends HistoryComparisonData {}

export const historyComparisonDataList: HistoryComparisonData[] = [
  {
    id: 'cmp-001',
    leftTaskId: 'task-1005',
    rightTaskId: 'task-1012',
    addedRiskIds: ['risk-1010'],
    removedRiskIds: ['risk-1005'],
    changedRiskIds: ['risk-1009'],
    summary: '河口片区新增 1 处待复核变化点，1 处低风险点消失。',
    createdAt: '2026-05-25T09:00:00Z'
  },
  {
    id: 'cmp-002',
    leftTaskId: 'task-1001',
    rightTaskId: 'task-1006',
    addedRiskIds: ['risk-1006'],
    removedRiskIds: ['risk-1002'],
    changedRiskIds: ['risk-1001'],
    summary: '滨海区域高风险点数量变化明显，需重点复盘。',
    createdAt: '2026-05-24T12:00:00Z'
  }
]

export function getAll(): HistoryComparisonData[] {
  return historyComparisonDataList
}

export function getById(id: string): HistoryComparisonData | undefined {
  return historyComparisonDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<HistoryComparisonFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): HistoryComparisonData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = historyComparisonDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.leftTaskId, item.rightTaskId, item.summary].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): HistoryComparisonData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_history_comparison_data')
  return raw ? (JSON.parse(raw) as HistoryComparisonData[]) : null
}

export function savePersisted(items: HistoryComparisonData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_history_comparison_data', JSON.stringify(items))
}

export function getByIdVO(id: string): HistoryComparisonVO | undefined {
  return getById(id)
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<HistoryComparisonFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): HistoryComparisonVO[] {
  return query(params)
}
      