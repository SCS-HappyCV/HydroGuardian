import { runtimeConfig } from '@/config/runtime'
import { Capacitor, CapacitorHttp } from '@capacitor/core'
import type { EvidencePhoto, LocationSnapshot } from '@/domain/fieldDraft'
import { evidenceFileService } from '@/services/evidenceFileService'
import type { RemoteArtifact, RemotePresignResult, RemoteWorkorder } from './remoteWorkorderTypes'

export class MobileApiError extends Error {
  constructor(message: string, public status = 0, public detail?: unknown) {
    super(message)
    this.name = 'MobileApiError'
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (Capacitor.isNativePlatform()) {
    try {
      const response = await CapacitorHttp.request({
        url: `${runtimeConfig.apiBaseUrl}${path}`,
        method: options.method || 'GET',
        headers: { Accept: 'application/json', ...(options.headers as Record<string, string> || {}) },
        data: typeof options.body === 'string' ? JSON.parse(options.body) : options.body,
        connectTimeout: 20_000,
        readTimeout: 20_000,
        responseType: 'json',
      })
      if (response.status < 200 || response.status >= 300) {
        const detail = response.data && typeof response.data === 'object' ? response.data.detail : undefined
        throw new MobileApiError(
          typeof detail === 'string' ? detail : `现场协同服务请求失败 (${response.status})`,
          response.status,
          detail,
        )
      }
      return response.data as T
    } catch (error) {
      if (error instanceof MobileApiError) throw error
      throw new MobileApiError('无法连接现场协同服务')
    }
  }
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), 20_000)
  try {
    const response = await fetch(`${runtimeConfig.apiBaseUrl}${path}`, {
      ...options,
      signal: options.signal || controller.signal,
      headers: { Accept: 'application/json', ...options.headers },
    })
    const payload: unknown = await response.json().catch(() => null)
    if (!response.ok) {
      const detail = payload && typeof payload === 'object' ? (payload as Record<string, unknown>).detail : undefined
      const message = typeof detail === 'string'
        ? detail
        : `现场协同服务请求失败 (${response.status})`
      throw new MobileApiError(message, response.status, detail)
    }
    return payload as T
  } catch (error) {
    if (error instanceof MobileApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new MobileApiError('现场协同服务响应超时')
    }
    throw new MobileApiError('无法连接现场协同服务')
  } finally {
    window.clearTimeout(timer)
  }
}

function post(body?: unknown, headers?: HeadersInit): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  }
}

async function uploadEvidencePhoto(photo: EvidencePhoto, workorder: RemoteWorkorder, kind: 'before' | 'after') {
  const filename = `${workorder.workorder_id}-${kind}-${photo.id}.${photo.mimeType === 'image/png' ? 'png' : 'jpg'}`
  const presigned = await request<RemotePresignResult>('/v1/assets/presign', post({
    filename,
    media_type: photo.mimeType,
    job_id: workorder.job_id,
    tenant_id: 'field-inspection',
  }))
  if (Capacitor.isNativePlatform()) {
    const response = await CapacitorHttp.put({
      url: presigned.upload_url,
      headers: { 'Content-Type': photo.mimeType },
      data: await evidenceFileService.readBase64(photo),
      dataType: 'file',
      connectTimeout: 20_000,
      readTimeout: 60_000,
    })
    if (response.status < 200 || response.status >= 300) {
      throw new MobileApiError('现场影像上传失败', response.status)
    }
  } else {
    const file = await evidenceFileService.readAsBlob(photo)
    const response = await fetch(presigned.upload_url, {
      method: 'PUT',
      headers: { 'Content-Type': photo.mimeType },
      body: file,
    })
    if (!response.ok) throw new MobileApiError('现场影像上传失败', response.status)
  }
  await request<RemoteArtifact>(`/v1/assets/${encodeURIComponent(presigned.artifact.artifact_id)}/complete`, post({
    metadata: {
      source: 'mobile_field_feedback',
      workorder_id: workorder.workorder_id,
      evidence_stage: kind,
      captured_at: photo.capturedAt,
    },
  }))
  return presigned.artifact.artifact_id
}

async function enrichEvidenceArtifacts(workorder: RemoteWorkorder) {
  const evidence = await Promise.all(workorder.evidence.map(async (item) => {
    if (!item.artifact_id) return item
    try {
      const artifact = await request<RemoteArtifact>(`/v1/assets/${encodeURIComponent(item.artifact_id)}`)
      return {
        ...item,
        media_type: artifact.media_type || item.media_type,
        metadata: {
          ...item.metadata,
          artifact_object_key: artifact.object_key,
          artifact_media_type: artifact.media_type,
          artifact_size_bytes: artifact.size_bytes,
          artifact_metadata: artifact.metadata,
        },
      }
    } catch {
      return item
    }
  }))
  return { ...workorder, evidence }
}

export const remoteWorkorderApi = {
  health: () => request<{ status: string }>('/healthz'),
  list: async () => (await request<{ workorders: RemoteWorkorder[] }>('/v1/workorders?limit=500')).workorders,
  get: async (workorderId: string) => enrichEvidenceArtifacts(
    await request<RemoteWorkorder>(`/v1/workorders/${encodeURIComponent(workorderId)}`),
  ),
  assign: (workorderId: string, assigneeUserId: string, actorUserId: string) => request<RemoteWorkorder>(
    `/v1/workorders/${encodeURIComponent(workorderId)}/assign`,
    post({ assignee_user_id: assigneeUserId, actor_user_id: actorUserId, note: '现场人员已接收任务' }),
  ),
  start: (workorderId: string, actorUserId: string) => request<RemoteWorkorder>(
    `/v1/workorders/${encodeURIComponent(workorderId)}/start`,
    post({ actor_user_id: actorUserId, note: '现场核查已开始' }),
  ),
  submitFeedback: async (workorder: RemoteWorkorder, input: {
    actorUserId: string
    note: string
    photos: EvidencePhoto[]
    location: LocationSnapshot | null
    idempotencyKey: string
    expectedVersion?: number
    uploadedArtifacts?: Record<string, string>
    onAssetState?: (photo: EvidencePhoto, state: 'uploading' | 'uploaded' | 'failed', artifactId?: string, error?: string) => Promise<void> | void
  }) => {
    const evidence = []
    for (const photo of input.photos) {
      let artifactId = input.uploadedArtifacts?.[photo.id]
      if (!artifactId) {
        await input.onAssetState?.(photo, 'uploading')
        try {
          artifactId = await uploadEvidencePhoto(photo, workorder, photo.kind)
          await input.onAssetState?.(photo, 'uploaded', artifactId)
        } catch (error) {
          await input.onAssetState?.(photo, 'failed', undefined, error instanceof Error ? error.message : '影像上传失败')
          throw error
        }
      }
      evidence.push({
        artifact_id: artifactId,
        title: photo.kind === 'before' ? '现场处置前影像' : '现场处置后影像',
        content: photo.kind === 'before' ? '现场核查基线证据' : '现场处置结果证据',
        metadata: {
          evidence_stage: photo.kind,
          captured_at: photo.capturedAt,
          location: input.location,
        },
      })
    }
    return request<RemoteWorkorder>(
      `/v1/workorders/${encodeURIComponent(workorder.workorder_id)}/feedback`,
      post({
        actor_user_id: input.actorUserId,
        note: input.note,
        evidence,
        client_submission_id: input.idempotencyKey,
        expected_version: input.expectedVersion ?? workorder.version,
      }, { 'Idempotency-Key': input.idempotencyKey }),
    )
  },
}
