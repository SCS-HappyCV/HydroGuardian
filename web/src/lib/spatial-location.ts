export interface SpatialLocationData {
  longitude: number
  latitude: number
  projectedX?: number
  projectedY?: number
  epsg?: number
  crsName?: string
  geographicBBox?: {
    west: number
    south: number
    east: number
    north: number
  }
}

export function formatGeographicCoordinate(location: SpatialLocationData, digits = 6): string {
  return `${location.longitude.toFixed(digits)}, ${location.latitude.toFixed(digits)}`
}

export function formatProjectedCoordinate(location: SpatialLocationData): string | undefined {
  if (!Number.isFinite(location.projectedX) || !Number.isFinite(location.projectedY)) return undefined
  return `${location.projectedX!.toFixed(3)}, ${location.projectedY!.toFixed(3)}`
}

export function distanceMeters(
  from: { longitude: number; latitude: number },
  to: { longitude: number; latitude: number },
): number {
  const radians = (value: number) => value * Math.PI / 180
  const radius = 6371008.8
  const deltaLatitude = radians(to.latitude - from.latitude)
  const deltaLongitude = radians(to.longitude - from.longitude)
  const latitudeA = radians(from.latitude)
  const latitudeB = radians(to.latitude)
  const value = Math.sin(deltaLatitude / 2) ** 2
    + Math.cos(latitudeA) * Math.cos(latitudeB) * Math.sin(deltaLongitude / 2) ** 2
  return radius * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value))
}

export function bearingDegrees(
  from: { longitude: number; latitude: number },
  to: { longitude: number; latitude: number },
): number {
  const radians = (value: number) => value * Math.PI / 180
  const latitudeA = radians(from.latitude)
  const latitudeB = radians(to.latitude)
  const deltaLongitude = radians(to.longitude - from.longitude)
  const y = Math.sin(deltaLongitude) * Math.cos(latitudeB)
  const x = Math.cos(latitudeA) * Math.sin(latitudeB)
    - Math.sin(latitudeA) * Math.cos(latitudeB) * Math.cos(deltaLongitude)
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360
}

export function directionLabel(degrees: number): string {
  const directions = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
  return directions[Math.round(degrees / 45) % directions.length]
}

export function mapViewUrl(location: SpatialLocationData): string {
  const { latitude, longitude } = location
  return `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=18/${latitude}/${longitude}`
}

export function mobileNavigationUrl(location: SpatialLocationData, label: string): string {
  const query = encodeURIComponent(label)
  return `geo:${location.latitude},${location.longitude}?q=${location.latitude},${location.longitude}(${query})`
}
