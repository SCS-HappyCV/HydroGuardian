import type { SettingData, SettingFilterKey } from './SettingData'

export interface SettingVO extends SettingData {}

export const settingDataList: SettingData[] = [
  { id: 'setting-001', key: 'systemName', value: 'HydroGuardian', category: 'basic', isSensitive: false, updatedAt: '2026-05-01T00:00:00Z' },
  { id: 'setting-002', key: 'defaultTimeRange', value: '24h', category: 'basic', isSensitive: false, updatedAt: '2026-05-01T00:00:00Z' },
  { id: 'setting-003', key: 'gisServiceUrl', value: 'https://api.hydroguardian.cn/gis', category: 'api', isSensitive: false, updatedAt: '2026-05-02T00:00:00Z' },
  { id: 'setting-004', key: 'modelServiceUrl', value: 'https://api.hydroguardian.cn/model', category: 'api', isSensitive: false, updatedAt: '2026-05-02T00:00:00Z' },
  { id: 'setting-005', key: 'apiKeyPrimary', value: 'hgk-live-81a2-xxxx', category: 'security', isSensitive: true, updatedAt: '2026-05-03T00:00:00Z' },
  { id: 'setting-006', key: 'dataRefreshInterval', value: '5m', category: 'data', isSensitive: false, updatedAt: '2026-05-03T00:00:00Z' }
]

export function getAll(): SettingData[] {
  return settingDataList
}

export function getById(id: string): SettingData | undefined {
  return settingDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<SettingFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): SettingData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = settingDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.key, item.value, item.category].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): SettingData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_setting_data')
  return raw ? (JSON.parse(raw) as SettingData[]) : null
}

export function savePersisted(items: SettingData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_setting_data', JSON.stringify(items))
}

export function getByIdVO(id: string): SettingVO | undefined {
  return getById(id)
}
