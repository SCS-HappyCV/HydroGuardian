import type { WorkorderReviewData, WorkorderReviewFilterKey } from './WorkorderReviewData'
import { getById as getUserById } from './UserService'

export interface WorkorderReviewVO extends WorkorderReviewData {
  reviewerUserName?: string
}

export const workorderReviewDataList: WorkorderReviewData[] = [
  { id: 'wrr-4001', orderId: 'wo-2002', reviewerUserId: 'user-004', decision: 'approved', comment: '处置措施完整，证据充分。', evidenceNote: '前后对比清晰，附图齐全。', createdAt: '2026-05-22T15:20:00Z' },
  { id: 'wrr-4002', orderId: 'wo-2005', reviewerUserId: 'user-004', decision: 'approved', comment: '复核结果符合预期。', evidenceNote: '变化点已消除。', createdAt: '2026-05-18T15:00:00Z' },
  { id: 'wrr-4003', orderId: 'wo-2006', reviewerUserId: 'user-002', decision: 'approved', comment: '整改已落实，建议关闭。', evidenceNote: '复检无异常。', createdAt: '2026-05-23T18:00:00Z' }
]

export function getAll(): WorkorderReviewData[] {
  return workorderReviewDataList
}

export function getById(id: string): WorkorderReviewData | undefined {
  return workorderReviewDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<WorkorderReviewFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): WorkorderReviewData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = workorderReviewDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.comment, item.evidenceNote, item.decision].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): WorkorderReviewData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_workorder_review_data')
  return raw ? (JSON.parse(raw) as WorkorderReviewData[]) : null
}

export function savePersisted(items: WorkorderReviewData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_workorder_review_data', JSON.stringify(items))
}

export function getByOrderIdVO(orderId: string): WorkorderReviewVO | undefined {
  const item = workorderReviewDataList.find((item) => item.orderId === orderId)
  if (!item) return undefined
  return {
    ...item,
    reviewerUserName: getUserById(item.reviewerUserId)?.name
  }
}
