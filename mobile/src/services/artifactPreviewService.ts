import { Capacitor, CapacitorHttp } from '@capacitor/core'

function contentType(headers: Record<string, string>) {
  const entry = Object.entries(headers).find(([key]) => key.toLowerCase() === 'content-type')
  return entry?.[1]?.split(';')[0] || 'image/webp'
}

export async function resolveArtifactPreview(url: string) {
  if (!Capacitor.isNativePlatform()) return url

  const response = await CapacitorHttp.get({
    url,
    headers: { Accept: 'image/avif,image/webp,image/png,image/jpeg,image/*' },
    connectTimeout: 15_000,
    readTimeout: 30_000,
    responseType: 'blob',
  })
  if (response.status < 200 || response.status >= 300) {
    throw new Error(`证据影像加载失败 (${response.status})`)
  }
  if (typeof response.data !== 'string' || !response.data) {
    throw new Error('证据影像数据无效')
  }
  if (response.data.startsWith('data:')) return response.data
  return `data:${contentType(response.headers)};base64,${response.data.replace(/\s/g, '')}`
}
