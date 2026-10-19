import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { Network } from '@capacitor/network'
import type { FieldDraft } from '@/domain/fieldDraft'
import type { MobileWorkOrder } from '@/domain/workorder'
import type { SyncRecord } from '@/domain/sync'
import { syncRepository } from '@/repositories/syncRepository'
import { runtimeConfig } from '@/config/runtime'
import { MobileApiError, remoteWorkorderApi } from '@/api/remoteWorkorderApi'
import { primaryFieldUser } from '@/domain/user'
import { fieldDraftRepository } from '@/repositories/fieldDraftRepository'
import { workorderRepository } from '@/repositories/workorderRepository'

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '现场反馈提交失败'
}

export const useSyncStore = defineStore('sync', () => {
  const records = ref<SyncRecord[]>([])
  const initialized = ref(false)
  const isConnected = ref(true)
  const retrying = ref(false)
  let networkListenerReady = false

  const pendingCount = computed(() => records.value.filter((item) => item.status === 'pending').length)
  const failedCount = computed(() => records.value.filter((item) => item.status === 'failed').length)
  const syncedCount = computed(() => records.value.filter((item) => item.status === 'synced').length)
  const photoCount = computed(() => records.value.reduce((total, item) => total + item.assetCount, 0))
  const latestSyncAt = computed(() => records.value
    .filter((item) => item.status === 'synced')
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0]?.updatedAt ?? null)

  async function persist() {
    await syncRepository.saveAll(records.value)
  }

  async function readNetworkStatus() {
    try {
      const status = await Network.getStatus()
      isConnected.value = status.connected
      return status.connected
    } catch {
      isConnected.value = false
      return false
    }
  }

  async function hydrate() {
    if (initialized.value) return
    records.value = await syncRepository.loadAll()
    await readNetworkStatus()
    initialized.value = true
    if (!networkListenerReady) {
      networkListenerReady = true
      await Network.addListener('networkStatusChange', (status) => {
        const reconnected = !isConnected.value && status.connected
        isConnected.value = status.connected
        if (reconnected) void retryAll()
      })
    }
    if (isConnected.value && records.value.some((item) => item.status !== 'synced')) {
      void retryAll()
    }
  }

  async function registerSubmission(workorder: MobileWorkOrder, draft: FieldDraft) {
    const connected = await readNetworkStatus()
    const now = new Date().toISOString()
    const record: SyncRecord = {
      id: `sync-${workorder.id}-${Date.now()}`,
      workorderId: workorder.id,
      title: workorder.title,
      assetCount: draft.photos.length,
      hasLocation: Boolean(draft.location),
      status: runtimeConfig.dataMode === 'remote' ? 'pending' : connected ? 'synced' : 'pending',
      createdAt: now,
      updatedAt: now,
      attemptCount: 0,
      submissionId: `field-feedback-${workorder.id}-${Date.now()}`,
      serverVersion: workorder.remoteVersion,
      assets: draft.photos.map((photo) => ({
        photoId: photo.id,
        kind: photo.kind,
        status: 'pending',
      })),
    }
    records.value.unshift(record)
    await persist()
    if (runtimeConfig.dataMode === 'remote' && connected) await submitRecord(record, workorder, draft)
    return record
  }

  async function submitRecord(record: SyncRecord, workorder: MobileWorkOrder, draft: FieldDraft) {
    record.attemptCount = (record.attemptCount || 0) + 1
    record.status = 'uploading'
    record.assets ||= draft.photos.map((photo) => ({ photoId: photo.id, kind: photo.kind, status: 'pending' }))
    record.updatedAt = new Date().toISOString()
    await persist()
    try {
      const remote = await remoteWorkorderApi.get(workorder.id)
      await remoteWorkorderApi.submitFeedback(remote, {
        actorUserId: primaryFieldUser.id,
        note: draft.note,
        photos: draft.photos,
        location: draft.location,
        idempotencyKey: record.submissionId || record.id,
        expectedVersion: record.serverVersion ?? remote.version,
        uploadedArtifacts: Object.fromEntries(
          record.assets.filter((item) => item.artifactId).map((item) => [item.photoId, item.artifactId!]),
        ),
        onAssetState: async (photo, state, artifactId, error) => {
          const asset = record.assets?.find((item) => item.photoId === photo.id)
          if (!asset) return
          asset.status = state === 'uploaded' ? 'uploaded' : state
          asset.artifactId = artifactId || asset.artifactId
          asset.lastError = error
          record.updatedAt = new Date().toISOString()
          await persist()
        },
      })
      record.status = 'synced'
      record.lastError = undefined
      record.updatedAt = new Date().toISOString()
      await persist()
      return true
    } catch (error) {
      if (error instanceof MobileApiError && error.status === 409) {
        try {
          const latest = await remoteWorkorderApi.get(workorder.id)
          const uploaded = new Set(record.assets?.flatMap((item) => item.artifactId ? [item.artifactId] : []) || [])
          const accepted = latest.status === 'review' && latest.evidence.some((item) => item.artifact_id && uploaded.has(item.artifact_id))
          if (accepted) {
            record.status = 'synced'
            record.lastError = undefined
            record.updatedAt = new Date().toISOString()
            await persist()
            return true
          }
        } catch {}
      }
      record.status = error instanceof MobileApiError && error.status === 409 ? 'conflict' : 'failed'
      record.lastError = errorMessage(error)
      record.updatedAt = new Date().toISOString()
      await persist()
      return false
    }
  }

  async function retry(recordId: string) {
    const record = records.value.find((item) => item.id === recordId)
    if (!record) return false
    const connected = await readNetworkStatus()
    if (!connected) {
      record.status = 'failed'
      record.lastError = '当前网络不可用'
      record.updatedAt = new Date().toISOString()
      await persist()
      return false
    }
    if (runtimeConfig.dataMode !== 'remote') {
      record.status = 'synced'
      record.lastError = undefined
      record.updatedAt = new Date().toISOString()
      await persist()
      return true
    }
    const [drafts, workorders] = await Promise.all([
      fieldDraftRepository.loadAll(),
      workorderRepository.load(),
    ])
    const draft = drafts.find((item) => item.workorderId === record.workorderId)
    const workorder = workorders?.find((item) => item.id === record.workorderId)
    if (!draft || !workorder) {
      record.status = 'failed'
      record.lastError = '设备内缺少对应的现场草稿'
      record.updatedAt = new Date().toISOString()
      await persist()
      return false
    }
    return submitRecord(record, workorder, draft)
  }

  async function retryAll() {
    if (retrying.value) return false
    retrying.value = true
    const retryable = records.value.filter((item) => item.status !== 'synced')
    try {
      const results = []
      for (const item of retryable) results.push(await retry(item.id))
      return results.every(Boolean)
    } finally {
      retrying.value = false
    }
  }

  async function clearAll() {
    await syncRepository.clear()
    records.value = []
  }

  return {
    records,
    initialized,
    isConnected,
    pendingCount,
    failedCount,
    syncedCount,
    photoCount,
    latestSyncAt,
    retrying,
    hydrate,
    registerSubmission,
    retry,
    retryAll,
    clearAll,
  }
})
