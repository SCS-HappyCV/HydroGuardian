import type { RiskLayerData, RiskLayerFilterKey } from './RiskLayerData'

export const riskLayerDataList: RiskLayerData[] = [
  { id: 'layer-001', name: '目标图层', iconName: 'Crosshair', isEnabled: true, sortOrder: 1 },
  { id: 'layer-002', name: '属性图层', iconName: 'SlidersHorizontal', isEnabled: true, sortOrder: 2 },
  { id: 'layer-003', name: '关系图层', iconName: 'Share2', isEnabled: true, sortOrder: 3 },
  { id: 'layer-004', name: '抑制图层', iconName: 'Ban', isEnabled: false, sortOrder: 4 }
]

export function getAll(): RiskLayerData[] {
  return riskLayerDataList
}

export function getById(id: string): RiskLayerData | undefined {
  return riskLayerDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<RiskLayerFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): RiskLayerData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = riskLayerDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.name, item.iconName].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): RiskLayerData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_risk_layer_data')
  return raw ? (JSON.parse(raw) as RiskLayerData[]) : null
}

export function savePersisted(items: RiskLayerData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_risk_layer_data', JSON.stringify(items))
}
