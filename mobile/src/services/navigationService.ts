import { Capacitor } from '@capacitor/core'

export const navigationService = {
  open(latitude: number, longitude: number, title: string) {
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || (!latitude && !longitude)) {
      throw new Error('当前任务缺少可导航的真实坐标')
    }
    const label = encodeURIComponent(title)
    if (Capacitor.getPlatform() === 'android') {
      window.location.href = `geo:${latitude},${longitude}?q=${latitude},${longitude}(${label})`
      return
    }
    window.open(`https://uri.amap.com/navigation?to=${longitude},${latitude},${label}&mode=car&policy=1&src=hydroguardian`, '_blank', 'noopener,noreferrer')
  },
}
