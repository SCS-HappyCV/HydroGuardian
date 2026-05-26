import type { SystemHealthData, SystemHealthFilterKey } from './SystemHealthData'

export interface SystemHealthVO extends SystemHealthData {}

export const systemHealthDataList: SystemHealthData[] = [
  { id: 'health-001', serviceKey: 'api-gateway', serviceName: 'API 网关', category: 'backend', status: 'healthy', latencyMs: 28, errorCount: 0, lastCheckedAt: '2026-05-25T07:50:00Z' },
  { id: 'health-002', serviceKey: 'task-engine', serviceName: '任务引擎', category: 'backend', status: 'degraded', latencyMs: 126, errorCount: 2, lastCheckedAt: '2026-05-25T07:50:00Z' },
  { id: 'health-003', serviceKey: 'risk-model', serviceName: '风险模型服务', category: 'model', status: 'healthy', latencyMs: 61, errorCount: 0, lastCheckedAt: '2026-05-25T07:50:00Z' },
  { id: 'health-004', serviceKey: 'gis-layer', serviceName: 'GIS 图层服务', category: 'backend', status: 'healthy', latencyMs: 44, errorCount: 0, lastCheckedAt: '2026-05-25T07:50:00Z' },
  { id: 'health-005', serviceKey: 'db-main', serviceName: '主数据库', category: 'database', status: 'healthy', latencyMs: 18, errorCount: 0, lastCheckedAt: '2026-05-25T07:50:00Z' },
  { id: 'health-006', serviceKey: 'notification', serviceName: '通知服务', category: 'backend', status: 'down', latencyMs: 0, errorCount: 5, lastCheckedAt: '2026-05-25T07:50:00Z' }
]

export function getAll(): SystemHealthData[] {
  return systemHealthDataList
}

export function getById(id: string): SystemHealthData | undefined {
  return systemHealthDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<SystemHealthFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): SystemHealthData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = systemHealthDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.serviceKey, item.serviceName, item.category, item.status].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): SystemHealthData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_system_health_data')
  return raw ? (JSON.parse(raw) as SystemHealthData[]) : null
}

export function savePersisted(items: SystemHealthData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_system_health_data', JSON.stringify(items))
}

export function getByIdVO(id: string): SystemHealthVO | undefined {
  return getById(id)
}

export function getAllVO(): SystemHealthVO[] {
  return systemHealthDataList
}
