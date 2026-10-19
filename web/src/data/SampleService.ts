import type { SampleData, SampleFilterKey } from './SampleData'
import { getById as getZoneById } from './ZoneService'

export interface SampleVO extends SampleData {
  zoneName?: string
}

export const sampleDataList: SampleData[] = [
  { id: 'sample-001', name: '河岸多模态场景 A', zoneId: 'zone-01', sampleType: 'image', collectedAt: '2026-05-24T07:50:00Z', status: 'available' },
  { id: 'sample-002', name: '西港岸线正射影像 B', zoneId: 'zone-05', sampleType: 'image', collectedAt: '2026-05-23T14:00:00Z', status: 'available' },
  { id: 'sample-003', name: '北岸点云场景 C', zoneId: 'zone-02', sampleType: 'image', collectedAt: '2026-05-25T00:50:00Z', status: 'available' },
  { id: 'sample-004', name: '中心河段变化影像 D', zoneId: 'zone-01', sampleType: 'image', collectedAt: '2026-05-22T10:40:00Z', status: 'archived' },
  { id: 'sample-005', name: '南堤高程场景 E', zoneId: 'zone-03', sampleType: 'image', collectedAt: '2026-05-24T19:20:00Z', status: 'available' },
  { id: 'sample-006', name: '东湾前后时相场景 F', zoneId: 'zone-04', sampleType: 'image', collectedAt: '2026-05-25T06:30:00Z', status: 'available' },
  { id: 'sample-007', name: '北岸岸线历史场景 G', zoneId: 'zone-02', sampleType: 'image', collectedAt: '2026-05-21T16:00:00Z', status: 'archived' },
  { id: 'sample-008', name: '南堤裸地快检场景 H', zoneId: 'zone-03', sampleType: 'image', collectedAt: '2026-05-20T08:40:00Z', status: 'available' }
]

export function getAll(): SampleData[] {
  return sampleDataList
}

export function getById(id: string): SampleData | undefined {
  return sampleDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<SampleFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): SampleData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = sampleDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.name, item.sampleType, item.status].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): SampleData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_sample_data')
  return raw ? (JSON.parse(raw) as SampleData[]) : null
}

export function savePersisted(items: SampleData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_sample_data', JSON.stringify(items))
}

export function getByIdVO(id: string): SampleVO | undefined {
  const item = getById(id)
  if (!item) return undefined
  return {
    ...item,
    zoneName: getZoneById(item.zoneId)?.name
  }
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<SampleFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): SampleVO[] {
  return query(params).map((item) => getByIdVO(item.id)).filter((item): item is SampleVO => Boolean(item))
}
