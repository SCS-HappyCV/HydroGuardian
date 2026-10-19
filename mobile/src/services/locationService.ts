import { Geolocation } from '@capacitor/geolocation'
import type { LocationSnapshot } from '@/domain/fieldDraft'

export class LocationCaptureError extends Error {}

export const locationService = {
  async capture(): Promise<LocationSnapshot> {
    try {
      let permissions = await Geolocation.checkPermissions()
      if (permissions.location === 'prompt' || permissions.location === 'prompt-with-rationale') {
        permissions = await Geolocation.requestPermissions({ permissions: ['location'] })
      }
      if (permissions.location !== 'granted') {
        throw new LocationCaptureError('未获得定位权限，请在系统设置中允许位置访问')
      }

      const position = await Geolocation.getCurrentPosition({
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 5000,
      })

      return {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: Math.round(position.coords.accuracy),
        capturedAt: new Date(position.timestamp).toISOString(),
      }
    } catch (error) {
      if (error instanceof LocationCaptureError) throw error
      throw new LocationCaptureError('定位失败，请确认系统定位服务已开启后重试')
    }
  },
}
