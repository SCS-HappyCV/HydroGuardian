export interface ZoneData {
  id: string
  name: string
  code: string
  level: 'city' | 'district' | 'site'
  parentZoneId?: string
  riskScore: number
  mapCenterLng: number
  mapCenterLat: number
  updatedAt: string
}

export type ZoneFilterKey = keyof Pick<ZoneData, 'level' | 'parentZoneId'>
