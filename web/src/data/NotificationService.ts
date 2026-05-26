import type { NotificationData, NotificationFilterKey } from './NotificationData'

export const notificationDataList: NotificationData[] = [
  { id: 'noti-001', title: '任务执行成功', content: '任务 task-1001 已完成并生成风险结果。', type: 'info', isRead: false, createdAt: '2026-05-24T08:18:30Z' },
  { id: 'noti-002', title: '任务失败提醒', content: '任务 task-1003 执行失败，请查看系统健康详情。', type: 'error', isRead: false, createdAt: '2026-05-24T19:36:20Z' },
  { id: 'noti-003', title: '工单待复核', content: '工单 wo-2002 已提交复核。', type: 'warning', isRead: true, createdAt: '2026-05-22T15:00:10Z' },
  { id: 'noti-004', title: '系统告警', content: '通知服务短暂不可用，已恢复。', type: 'warning', isRead: false, createdAt: '2026-05-25T07:41:00Z' }
]

export function getAll(): NotificationData[] {
  return notificationDataList
}

export function getById(id: string): NotificationData | undefined {
  return notificationDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<NotificationFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): NotificationData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = notificationDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.title, item.content, item.type].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): NotificationData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_notification_data')
  return raw ? (JSON.parse(raw) as NotificationData[]) : null
}

export function savePersisted(items: NotificationData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_notification_data', JSON.stringify(items))
}
