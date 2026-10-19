import type { EvidencePhotoKind } from './fieldDraft'

export type SyncRecordStatus = 'pending' | 'uploading' | 'synced' | 'failed' | 'conflict'
export type SyncAssetStatus = 'pending' | 'uploading' | 'uploaded' | 'failed'

export interface SyncAssetRecord {
  photoId: string
  kind: EvidencePhotoKind
  status: SyncAssetStatus
  artifactId?: string
  lastError?: string
}

export interface SyncRecord {
  id: string
  workorderId: string
  title: string
  assetCount: number
  hasLocation: boolean
  status: SyncRecordStatus
  createdAt: string
  updatedAt: string
  attemptCount?: number
  lastError?: string
  submissionId?: string
  serverVersion?: number
  assets?: SyncAssetRecord[]
}

export const syncStatusLabels: Record<SyncRecordStatus, string> = {
  pending: '等待提交',
  uploading: '正在上传',
  synced: '已提交',
  failed: '提交失败',
  conflict: '状态冲突',
}
