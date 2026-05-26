import type { UserData, UserFilterKey } from './UserData'
import { getById as getRoleById } from './RoleService'
import { getById as getProjectById } from './ProjectService'
import { getById as getDatasetById } from './DatasetService'

export interface UserVO extends UserData {
  roleName?: string
  projectName?: string
  datasetName?: string
}

export const userDataList: UserData[] = [
  { id: 'user-001', name: '林澄', email: 'lincheng@hydroguardian.cn', roleId: 'role-001', projectId: 'proj-001', datasetId: 'dataset-001', status: 'active', avatarUrl: 'https://spark-builder.s3.cn-north-1.amazonaws.com.cn/image/2026/5/25/b63a2be1-761c-4ff4-a765-8418ead3a576.png', createdAt: '2026-03-01T08:00:00Z', updatedAt: '2026-05-20T08:00:00Z' },
  { id: 'user-002', name: '许然', email: 'xuran@hydroguardian.cn', roleId: 'role-002', projectId: 'proj-001', datasetId: 'dataset-002', status: 'active', avatarUrl: 'https://spark-builder.s3.cn-north-1.amazonaws.com.cn/image/2026/5/25/cac3d753-c9b6-4eac-a4c5-f2f586d8955f.png', createdAt: '2026-03-02T08:00:00Z', updatedAt: '2026-05-20T08:00:00Z' },
  { id: 'user-003', name: '周启明', email: 'zhouqiming@hydroguardian.cn', roleId: 'role-003', projectId: 'proj-002', datasetId: 'dataset-003', status: 'active', avatarUrl: 'https://spark-builder.s3.cn-north-1.amazonaws.com.cn/image/2026/5/25/2c02d539-4775-4e43-86c0-23ffc00fc486.png', createdAt: '2026-03-03T08:00:00Z', updatedAt: '2026-05-21T08:00:00Z' },
  { id: 'user-004', name: '顾语彤', email: 'guyutong@hydroguardian.cn', roleId: 'role-004', projectId: 'proj-002', datasetId: 'dataset-001', status: 'active', avatarUrl: 'https://spark-builder.s3.cn-north-1.amazonaws.com.cn/image/2026/5/25/06ff79b1-74e3-4183-8ec8-86ab16324be1.png', createdAt: '2026-03-04T08:00:00Z', updatedAt: '2026-05-21T08:00:00Z' }
]

export function getAll(): UserData[] {
  return userDataList
}

export function getById(id: string): UserData | undefined {
  return userDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<UserFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): UserData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = userDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.name, item.email].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): UserData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_user_data')
  return raw ? (JSON.parse(raw) as UserData[]) : null
}

export function savePersisted(items: UserData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_user_data', JSON.stringify(items))
}

export function getByIdVO(id: string): UserVO | undefined {
  const item = getById(id)
  if (!item) return undefined
  return {
    ...item,
    roleName: getRoleById(item.roleId)?.name,
    projectName: getProjectById(item.projectId)?.name,
    datasetName: getDatasetById(item.datasetId)?.name
  }
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<UserFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): UserVO[] {
  return query(params).map((item) => getByIdVO(item.id)).filter((item): item is UserVO => Boolean(item))
}
