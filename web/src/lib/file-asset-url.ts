// 文件资源地址工具：统一处理后端返回的绝对地址、API 相对路径和空地址。

import { API_CONFIG } from '@/lib/api-contracts'

// 将后端 FileAsset.downloadUrl 解析成浏览器可访问地址。
export function resolveFileDownloadUrl(downloadUrl?: string | null): string {
  if (!downloadUrl) return ''
  if (/^(https?:\/\/|data:|blob:)/i.test(downloadUrl)) return downloadUrl
  if (downloadUrl.startsWith('/')) {
    return typeof window === 'undefined' ? downloadUrl : new URL(downloadUrl, window.location.origin).toString()
  }

  try {
    return new URL(downloadUrl, `${API_CONFIG.baseUrl}/`).toString()
  } catch {
    return downloadUrl
  }
}
