import type { RoleData, RoleFilterKey } from './RoleData'

export interface RoleVO extends RoleData {}

export const roleDataList: RoleData[] = [
  { id: 'role-001', name: '平台管理员', code: 'admin', description: '管理系统配置、权限与健康状态。', permissionCount: 24, isSystem: true, createdAt: '2026-03-01T00:00:00Z', updatedAt: '2026-05-01T00:00:00Z' },
  { id: 'role-002', name: '巡检负责人', code: 'inspector', description: '发起任务、处理工单与查看风险。', permissionCount: 16, isSystem: false, createdAt: '2026-03-02T00:00:00Z', updatedAt: '2026-05-02T00:00:00Z' },
  { id: 'role-003', name: '风险分析师', code: 'analyst', description: '分析风险结果并维护知识库。', permissionCount: 18, isSystem: false, createdAt: '2026-03-03T00:00:00Z', updatedAt: '2026-05-03T00:00:00Z' },
  { id: 'role-004', name: '复核经理', code: 'reviewer', description: '审核工单处理结果并决定关闭。', permissionCount: 12, isSystem: false, createdAt: '2026-03-04T00:00:00Z', updatedAt: '2026-05-04T00:00:00Z' }
]

export function getAll(): RoleData[] {
  return roleDataList
}

export function getById(id: string): RoleData | undefined {
  return roleDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<RoleFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): RoleData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = roleDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.name, item.code, item.description].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): RoleData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_role_data')
  return raw ? (JSON.parse(raw) as RoleData[]) : null
}

export function savePersisted(items: RoleData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_role_data', JSON.stringify(items))
}

export function getByIdVO(id: string): RoleVO | undefined {
  return getById(id)
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<RoleFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): RoleVO[] {
  return query(params)
}
