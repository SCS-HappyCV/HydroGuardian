import type { ZoneData, ZoneFilterKey } from './ZoneData'

export interface ZoneVO extends ZoneData {}

export const zoneDataList: ZoneData[] = [
  { id: 'zone-01', name: '滨海新区', code: 'ZH-01', level: 'city', riskScore: 82, mapCenterLng: 119.123, mapCenterLat: 32.456, updatedAt: '2026-05-25T00:00:00Z' },
  { id: 'zone-02', name: '北岸排水片区', code: 'ZH-02', level: 'district', parentZoneId: 'zone-01', riskScore: 77, mapCenterLng: 119.223, mapCenterLat: 32.356, updatedAt: '2026-05-25T00:00:00Z' },
  { id: 'zone-03', name: '南堤闸门站', code: 'ZH-03', level: 'site', parentZoneId: 'zone-01', riskScore: 91, mapCenterLng: 119.323, mapCenterLat: 32.256, updatedAt: '2026-05-25T00:00:00Z' },
  { id: 'zone-04', name: '东湾片区', code: 'ZH-04', level: 'district', parentZoneId: 'zone-01', riskScore: 66, mapCenterLng: 119.423, mapCenterLat: 32.156, updatedAt: '2026-05-25T00:00:00Z' },
  { id: 'zone-05', name: '西港工业区', code: 'ZH-05', level: 'site', parentZoneId: 'zone-01', riskScore: 54, mapCenterLng: 119.523, mapCenterLat: 32.056, updatedAt: '2026-05-25T00:00:00Z' },
  { id: 'zone-06', name: '河口片区', code: 'ZH-06', level: 'district', parentZoneId: 'zone-01', riskScore: 61, mapCenterLng: 119.623, mapCenterLat: 31.956, updatedAt: '2026-05-25T00:00:00Z' }
]

export function getAll(): ZoneData[] {
  return zoneDataList
}

export function getById(id: string): ZoneData | undefined {
  return zoneDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<ZoneFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): ZoneData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = zoneDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.name, item.code, item.level].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): ZoneData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_zone_data')
  return raw ? (JSON.parse(raw) as ZoneData[]) : null
}

export function savePersisted(items: ZoneData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_zone_data', JSON.stringify(items))
}

export function getByIdVO(id: string): ZoneVO | undefined {
  return getById(id)
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<ZoneFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): ZoneVO[] {
  return query(params)
}
