
import type { WorkorderEvidenceData, WorkorderEvidenceFilterKey } from './WorkorderEvidenceData'

export interface WorkorderEvidenceVO extends WorkorderEvidenceData {}

export const workorderEvidenceDataList: WorkorderEvidenceData[] = [
  {
    id: 'evi-001',
    orderId: 'wo-2001',
    evidenceType: 'before',
    title: '处理前现场照片',
    content: '滨海泵站夜间水位上升，边缘区域存在明显反光。',
    createdAt: '2026-05-24T08:22:00Z'
  },
  {
    id: 'evi-002',
    orderId: 'wo-2001',
    evidenceType: 'after',
    title: '处理后现场照片',
    content: '完成初步核验后，局部积水已下降。',
    createdAt: '2026-05-24T09:05:00Z'
  },
  {
    id: 'evi-003',
    orderId: 'wo-2002',
    evidenceType: 'before',
    title: '桥涵积水前图',
    content: '桥涵下穿点积水深度明显超过阈值。',
    createdAt: '2026-05-22T11:15:00Z'
  },
  {
    id: 'evi-004',
    orderId: 'wo-2002',
    evidenceType: 'after',
    title: '桥涵积水后图',
    content: '清理后积水明显回落，车流恢复通行。',
    createdAt: '2026-05-22T14:50:00Z'
  }
]

export function getAll(): WorkorderEvidenceData[] {
  return workorderEvidenceDataList
}

export function getById(id: string): WorkorderEvidenceData | undefined {
  return workorderEvidenceDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<WorkorderEvidenceFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): WorkorderEvidenceData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = workorderEvidenceDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.title, item.content, item.evidenceType].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): WorkorderEvidenceData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_workorder_evidence_data')
  return raw ? (JSON.parse(raw) as WorkorderEvidenceData[]) : null
}

export function savePersisted(items: WorkorderEvidenceData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_workorder_evidence_data', JSON.stringify(items))
}
      