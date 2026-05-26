import type { ProjectData, ProjectFilterKey } from './ProjectData'

export interface ProjectVO extends ProjectData {}

export const projectDataList: ProjectData[] = [
  { id: 'proj-001', name: '滨海防汛项目', code: 'HG-001', region: '滨海新区', status: 'active', createdAt: '2026-02-01T00:00:00Z', updatedAt: '2026-05-01T00:00:00Z' },
  { id: 'proj-002', name: '中心城区排涝项目', code: 'HG-002', region: '中心城区', status: 'active', createdAt: '2026-02-05T00:00:00Z', updatedAt: '2026-05-01T00:00:00Z' }
]

export function getAll(): ProjectData[] {
  return projectDataList
}

export function getById(id: string): ProjectData | undefined {
  return projectDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<ProjectFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): ProjectData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = projectDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.name, item.code, item.region].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): ProjectData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_project_data')
  return raw ? (JSON.parse(raw) as ProjectData[]) : null
}

export function savePersisted(items: ProjectData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_project_data', JSON.stringify(items))
}

export function getByIdVO(id: string): ProjectVO | undefined {
  return getById(id)
}
