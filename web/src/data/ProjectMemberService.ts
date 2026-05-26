
import type { ProjectMemberData, ProjectMemberFilterKey } from './ProjectMemberData'

export interface ProjectMemberVO extends ProjectMemberData {}

export const projectMemberDataList: ProjectMemberData[] = [
  { id: 'pm-001', projectId: 'proj-001', userId: 'user-001', roleId: 'role-001', assignedAt: '2026-03-01T08:00:00Z', status: 'active' },
  { id: 'pm-002', projectId: 'proj-001', userId: 'user-002', roleId: 'role-002', assignedAt: '2026-03-02T08:00:00Z', status: 'active' },
  { id: 'pm-003', projectId: 'proj-002', userId: 'user-003', roleId: 'role-003', assignedAt: '2026-03-03T08:00:00Z', status: 'active' },
  { id: 'pm-004', projectId: 'proj-002', userId: 'user-004', roleId: 'role-004', assignedAt: '2026-03-04T08:00:00Z', status: 'active' }
]

export function getAll(): ProjectMemberData[] {
  return projectMemberDataList
}

export function getById(id: string): ProjectMemberData | undefined {
  return projectMemberDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<ProjectMemberFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): ProjectMemberData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = projectMemberDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.projectId, item.userId, item.roleId].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): ProjectMemberData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_project_member_data')
  return raw ? (JSON.parse(raw) as ProjectMemberData[]) : null
}

export function savePersisted(items: ProjectMemberData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_project_member_data', JSON.stringify(items))
}
      