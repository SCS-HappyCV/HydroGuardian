import type { SystemLogData, SystemLogFilterKey } from './SystemLogData'

export interface SystemLogVO extends SystemLogData {}

export const systemLogDataList: SystemLogData[] = [
  { id: 'slog-5001', serviceHealthId: 'health-002', taskId: 'task-1003', level: 'error', message: '任务引擎超时，已触发一次重试。', createdAt: '2026-05-24T19:35:42Z' },
  { id: 'slog-5002', serviceHealthId: 'health-006', level: 'error', message: '通知服务不可用，部分提醒延迟发送。', createdAt: '2026-05-25T07:40:00Z' },
  { id: 'slog-5003', serviceHealthId: 'health-002', taskId: 'task-1002', level: 'warn', message: '处理排队延迟上升，资源占用偏高。', createdAt: '2026-05-25T01:20:00Z' },
  { id: 'slog-5004', serviceHealthId: 'health-003', taskId: 'task-1001', level: 'info', message: '风险模型服务推理完成。', createdAt: '2026-05-24T08:15:18Z' }
]

export function getAll(): SystemLogData[] {
  return systemLogDataList
}

export function getById(id: string): SystemLogData | undefined {
  return systemLogDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<SystemLogFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): SystemLogData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = systemLogDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.message, item.level].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): SystemLogData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_system_log_data')
  return raw ? (JSON.parse(raw) as SystemLogData[]) : null
}

export function savePersisted(items: SystemLogData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_system_log_data', JSON.stringify(items))
}

export function queryByServiceHealthId(serviceHealthId: string): SystemLogVO[] {
  return systemLogDataList.filter((item) => item.serviceHealthId === serviceHealthId)
}
