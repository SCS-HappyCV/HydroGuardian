
import type { WorkorderEvidenceData, WorkorderEvidenceFilterKey } from './WorkorderEvidenceData'

const STORAGE_KEY = 'hydroguardian_workorder_evidence_data_competition_v1'

export interface WorkorderEvidenceVO extends WorkorderEvidenceData {}

export const workorderEvidenceDataList: WorkorderEvidenceData[] = [
  {
    id: 'evi-001',
    orderId: 'wo-2001',
    evidenceType: 'before',
    title: 'AI 发现区域正射影像',
    content: '风险框内呈连续细长裸露形态，距水线约 18 米，疑似新开挖沟渠。',
    createdAt: '2026-05-24T08:22:00Z'
  },
  {
    id: 'evi-002',
    orderId: 'wo-2001',
    evidenceType: 'after',
    title: '现场处置完成影像',
    content: '现场确认存在新近开挖沟渠，完成警戒与回填处置，复测后未见继续扩展。',
    createdAt: '2026-05-24T10:42:00Z'
  },
  {
    id: 'evi-005',
    orderId: 'wo-2001',
    evidenceType: 'note',
    title: '点云与时相变化证据',
    content: '局部高差 1.8 米，长宽比 6.4；变化掩膜与沟渠轮廓重合度 91%。',
    createdAt: '2026-05-24T08:22:30Z'
  },
  {
    id: 'evi-003',
    orderId: 'wo-2002',
    evidenceType: 'before',
    title: '扰动发生前影像',
    content: '历史影像中该岸线区域植被覆盖连续，未出现裸露扰动。',
    createdAt: '2026-05-22T11:15:00Z'
  },
  {
    id: 'evi-004',
    orderId: 'wo-2002',
    evidenceType: 'after',
    title: '扰动发生后影像',
    content: '本期影像出现连续裸露区域，变化掩膜与风险轮廓一致。',
    createdAt: '2026-05-22T14:50:00Z'
  }
]

export function getAll(): WorkorderEvidenceData[] {
  return loadPersisted() || workorderEvidenceDataList
}

export function getById(id: string): WorkorderEvidenceData | undefined {
  return getAll().find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<WorkorderEvidenceFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): WorkorderEvidenceData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = getAll().filter((item) => {
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
  const raw = localStorage.getItem(STORAGE_KEY)
  return raw ? (JSON.parse(raw) as WorkorderEvidenceData[]) : null
}

export function savePersisted(items: WorkorderEvidenceData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
}
