
import type { AttachmentData, AttachmentFilterKey } from './AttachmentData'

export interface AttachmentVO extends AttachmentData {}

export const attachmentDataList: AttachmentData[] = [
  {
    id: 'att-001',
    orderId: 'wo-2001',
    fileName: '滨海泵站现场照片 1.jpg',
    fileType: 'image',
    url: 'https://spark-builder.s3.cn-north-1.amazonaws.com.cn/image/2026/5/26/39fe6445-b59c-4e4a-a513-013837a8bd71.jpeg',
    uploadedByUserId: 'user-002',
    uploadedAt: '2026-05-24T09:05:00Z'
  },
  {
    id: 'att-002',
    orderId: 'wo-2001',
    fileName: '复核说明.pdf',
    fileType: 'pdf',
    url: 'https://example.invalid/files/wo-2001-review.pdf',
    uploadedByUserId: 'user-002',
    uploadedAt: '2026-05-24T09:08:00Z'
  },
  {
    id: 'att-003',
    orderId: 'wo-2002',
    fileName: '桥涵积水前后对比.png',
    fileType: 'image',
    url: 'https://spark-builder.s3.cn-north-1.amazonaws.com.cn/image/2026/5/26/1c3a47d2-bfa9-44ec-9c6d-87a112d55244.jpeg',
    uploadedByUserId: 'user-003',
    uploadedAt: '2026-05-22T14:40:00Z'
  },
  {
    id: 'att-004',
    orderId: 'wo-2002',
    fileName: '处置记录.doc',
    fileType: 'doc',
    url: 'https://example.invalid/files/wo-2002-disposal.doc',
    uploadedByUserId: 'user-003',
    uploadedAt: '2026-05-22T14:55:00Z'
  }
]

export function getAll(): AttachmentData[] {
  return attachmentDataList
}

export function getById(id: string): AttachmentData | undefined {
  return attachmentDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<AttachmentFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): AttachmentData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = attachmentDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.fileName, item.fileType].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): AttachmentData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_attachment_data')
  return raw ? (JSON.parse(raw) as AttachmentData[]) : null
}

export function savePersisted(items: AttachmentData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_attachment_data', JSON.stringify(items))
}
      