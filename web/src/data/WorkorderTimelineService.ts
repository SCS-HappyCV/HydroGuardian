import type { WorkorderTimelineData, WorkorderTimelineFilterKey } from './WorkorderTimelineData'
import { getById as getUserById } from './UserService'

export interface WorkorderTimelineVO extends WorkorderTimelineData {
  actorUserName?: string
}

export const workorderTimelineDataList: WorkorderTimelineData[] = [
  { id: 'wot-3001', orderId: 'wo-2001', actorUserId: 'user-001', action: 'created', note: '基于滨海泵站风险自动创建工单。', createdAt: '2026-05-24T08:20:00Z' },
  { id: 'wot-3002', orderId: 'wo-2001', actorUserId: 'user-002', action: 'assigned', note: '已分配给现场巡检负责人。', createdAt: '2026-05-24T08:25:00Z' },
  { id: 'wot-3003', orderId: 'wo-2001', actorUserId: 'user-002', action: 'processing', note: '完成初步核验，正在补充附件。', createdAt: '2026-05-24T09:00:00Z' },
  { id: 'wot-3004', orderId: 'wo-2002', actorUserId: 'user-003', action: 'created', note: '桥涵积水风险已生成工单。', createdAt: '2026-05-22T11:12:00Z' },
  { id: 'wot-3005', orderId: 'wo-2002', actorUserId: 'user-003', action: 'processing', note: '现场处置开始，等待复核材料。', createdAt: '2026-05-22T12:20:00Z' },
  { id: 'wot-3006', orderId: 'wo-2002', actorUserId: 'user-004', action: 'review_requested', note: '已申请复核。', createdAt: '2026-05-22T15:00:00Z' },
  { id: 'wot-3007', orderId: 'wo-2003', actorUserId: 'user-001', action: 'created', note: '高新区高风险点自动生成待办工单。', createdAt: '2026-05-20T09:06:00Z' },
  { id: 'wot-3008', orderId: 'wo-2004', actorUserId: 'user-002', action: 'assigned', note: '责任人已指派，预计当日完成。', createdAt: '2026-05-25T01:35:00Z' },
  { id: 'wot-3009', orderId: 'wo-2004', actorUserId: 'user-002', action: 'processing', note: '清淤工作推进中。', createdAt: '2026-05-25T02:10:00Z' },
  { id: 'wot-3010', orderId: 'wo-2005', actorUserId: 'user-004', action: 'closed', note: '复核通过后已关闭。', createdAt: '2026-05-18T15:00:00Z' },
  { id: 'wot-3011', orderId: 'wo-2006', actorUserId: 'user-002', action: 'reviewed', note: '整改结果已通过审核。', createdAt: '2026-05-23T18:00:00Z' },
  { id: 'wot-3012', orderId: 'wo-2006', actorUserId: 'user-003', action: 'closed', note: '工单已关闭。', createdAt: '2026-05-23T18:05:00Z' }
]

export function getAll(): WorkorderTimelineData[] {
  return workorderTimelineDataList
}

export function getById(id: string): WorkorderTimelineData | undefined {
  return workorderTimelineDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<WorkorderTimelineFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): WorkorderTimelineData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = workorderTimelineDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.note, item.action].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): WorkorderTimelineData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_workorder_timeline_data')
  return raw ? (JSON.parse(raw) as WorkorderTimelineData[]) : null
}

export function savePersisted(items: WorkorderTimelineData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_workorder_timeline_data', JSON.stringify(items))
}

export function queryByOrderId(orderId: string): WorkorderTimelineVO[] {
  return workorderTimelineDataList
    .filter((item) => item.orderId === orderId)
    .map((item) => ({ ...item, actorUserName: getUserById(item.actorUserId)?.name }))
}
