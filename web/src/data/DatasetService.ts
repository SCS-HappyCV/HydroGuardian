import type { DatasetData, DatasetFilterKey } from './DatasetData'

export interface DatasetVO extends DatasetData {}

export const datasetDataList: DatasetData[] = [
  { id: 'dataset-001', name: '正射影像场景集', code: 'DS-001', description: '用于候选区域定位、纹理识别和风险叠加展示。', sourceType: 'gis', status: 'ready', createdAt: '2026-02-10T00:00:00Z', updatedAt: '2026-05-01T00:00:00Z' },
  { id: 'dataset-002', name: '点云与几何特征集', code: 'DS-002', description: '用于高程、坡度、形态和空间关系证据计算。', sourceType: 'manual', status: 'ready', createdAt: '2026-02-11T00:00:00Z', updatedAt: '2026-05-01T00:00:00Z' },
  { id: 'dataset-003', name: '前后时相影像集', code: 'DS-003', description: '用于岸线变化检测和变化掩膜生成。', sourceType: 'gis', status: 'syncing', createdAt: '2026-02-12T00:00:00Z', updatedAt: '2026-05-02T00:00:00Z' }
]

export function getAll(): DatasetData[] {
  return datasetDataList
}

export function getById(id: string): DatasetData | undefined {
  return datasetDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<DatasetFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): DatasetData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = datasetDataList.filter((item) => {
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

export function loadPersisted(): DatasetData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_dataset_data')
  return raw ? (JSON.parse(raw) as DatasetData[]) : null
}

export function savePersisted(items: DatasetData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_dataset_data', JSON.stringify(items))
}

export function getByIdVO(id: string): DatasetVO | undefined {
  return getById(id)
}
