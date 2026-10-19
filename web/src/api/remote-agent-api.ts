import type { RemoteAgentEvent, RemoteAgentHealth, RemoteAgentJob, RemoteAgentStep, RemoteAgentWorker, RemoteArtifactRecord, RemoteInterventionResponse, RemoteJobSubmission, RemoteMessageListResponse, RemoteMessageResponse, RemotePresignResult, RemoteTaskRecord } from '@/lib/remote-agent-types'
import type { RemoteWorkorder } from '@/lib/remote-workorder-types'
import type { RemoteAuditReport } from '@/lib/remote-audit-report'

const BASE_URL = (import.meta.env.VITE_REMOTE_AGENT_BASE_URL || '/hydro-api').replace(/\/$/, '')

export class RemoteAgentApiError extends Error {
  constructor(message: string, public status: number, public detail?: unknown) { super(message); this.name = 'RemoteAgentApiError' }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15_000)
  try {
    const response = await fetch(`${BASE_URL}${path}`, { ...options, signal: options.signal || controller.signal, headers: { Accept: 'application/json', ...options.headers } })
    const payload: any = await response.json().catch((): null => null)
    if (!response.ok) {
      const detail = payload?.detail
      const message = typeof detail === 'string' ? detail : detail?.message || `Agent 服务请求失败 (${response.status})`
      throw new RemoteAgentApiError(message, response.status, detail)
    }
    return payload as T
  } finally {
    clearTimeout(timeout)
  }
}

function jsonOptions(method: 'POST' | 'PUT', body?: unknown, headers?: HeadersInit): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json', ...headers }, body: body === undefined ? undefined : JSON.stringify(body) }
}

export const remoteAgentApi = {
  health: () => request<RemoteAgentHealth>('/healthz'),
  workers: async () => (await request<{ workers: RemoteAgentWorker[] }>('/v1/workers')).workers,
  createJob: (submission: RemoteJobSubmission, idempotencyKey: string) => request<RemoteAgentJob>('/v1/jobs', jsonOptions('POST', submission, { 'Idempotency-Key': idempotencyKey })),
  getJob: (jobId: string) => request<RemoteAgentJob>(`/v1/jobs/${encodeURIComponent(jobId)}`),
  getSteps: async (jobId: string) => (await request<{ steps: RemoteAgentStep[] }>(`/v1/jobs/${encodeURIComponent(jobId)}/steps`)).steps,
  getEvents: async (jobId: string) => (await request<{ events: RemoteAgentEvent[] }>(`/v1/jobs/${encodeURIComponent(jobId)}/events`)).events,
  getMessages: (jobId: string) => request<RemoteMessageListResponse>(`/v1/jobs/${encodeURIComponent(jobId)}/messages`),
  sendMessage: (jobId: string, input: { intent?: 'auto' | 'ask' | 'append_context'; content: string }, idempotencyKey: string) => request<RemoteMessageResponse>(`/v1/jobs/${encodeURIComponent(jobId)}/messages`, jsonOptions('POST', input, { 'Idempotency-Key': idempotencyKey })),
  interveneJob: (jobId: string, input: { action: 'cancel' | 'replan'; content?: string; confirmed: true }, idempotencyKey: string) => request<RemoteInterventionResponse>(`/v1/jobs/${encodeURIComponent(jobId)}/interventions`, jsonOptions('POST', input, { 'Idempotency-Key': idempotencyKey })),
  getArtifacts: async (jobId: string) => (await request<{ artifacts: Record<string, string> }>(`/v1/jobs/${encodeURIComponent(jobId)}/artifacts`)).artifacts,
  getAuditReport: (jobId: string) => request<RemoteAuditReport>(`/v1/reports/jobs/${encodeURIComponent(jobId)}`),
  listTasks: async (params: { status?: string; zone_id?: string; keyword?: string; limit?: string } = {}) => {
    const query = new URLSearchParams(Object.entries(params).filter((entry): entry is [string, string] => Boolean(entry[1])))
    return (await request<{ tasks: RemoteTaskRecord[] }>(`/v1/tasks${query.size ? `?${query}` : ''}`)).tasks
  },
  getTask: (taskId: string) => request<RemoteTaskRecord>(`/v1/tasks/${encodeURIComponent(taskId)}`),
  cancelJob: (jobId: string) => request<RemoteAgentJob>(`/v1/jobs/${encodeURIComponent(jobId)}/cancel`, jsonOptions('POST')),
  retryJob: (jobId: string) => request<RemoteAgentJob>(`/v1/jobs/${encodeURIComponent(jobId)}/retry`, jsonOptions('POST')),
  presignUpload: (input: { filename: string; media_type?: string; tenant_id?: string; job_id?: string }) => request<RemotePresignResult>('/v1/assets/presign', jsonOptions('POST', input)),
  uploadFile: async (uploadUrl: string, file: File) => { const response = await fetch(uploadUrl, { method: 'PUT', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file }); if (!response.ok) throw new RemoteAgentApiError('文件上传失败', response.status) },
  completeUpload: (artifactId: string, metadata: Record<string, unknown> = {}) => request<RemoteArtifactRecord>(`/v1/assets/${encodeURIComponent(artifactId)}/complete`, jsonOptions('POST', { metadata })),
  getArtifact: (artifactId: string) => request<RemoteArtifactRecord>(`/v1/assets/${encodeURIComponent(artifactId)}`),
  getDownloadUrl: async (artifactId: string) => (await request<{ download_url: string }>(`/v1/assets/${encodeURIComponent(artifactId)}/download`)).download_url,
  getPreviewUrl: (artifactId: string, maxDimension = 2048) => `${BASE_URL}/v1/assets/${encodeURIComponent(artifactId)}/preview?max_dimension=${maxDimension}`,
  createWorkorder: (input: { job_id: string; candidate_id: string; region_id?: string; task_id?: string; priority?: string; due_at?: string; location?: Record<string, unknown> }) => request<RemoteWorkorder>('/v1/workorders', jsonOptions('POST', input)),
  listWorkorders: async (params: { status?: string; task_id?: string; job_id?: string } = {}) => {
    const query = new URLSearchParams(Object.entries(params).filter((entry): entry is [string, string] => Boolean(entry[1])))
    return (await request<{ workorders: RemoteWorkorder[] }>(`/v1/workorders${query.size ? `?${query}` : ''}`)).workorders
  },
  getWorkorder: (workorderId: string) => request<RemoteWorkorder>(`/v1/workorders/${encodeURIComponent(workorderId)}`),
  assignWorkorder: (workorderId: string, input: { assignee_user_id: string; reviewer_user_id?: string; due_at?: string; actor_user_id?: string; note?: string }) => request<RemoteWorkorder>(`/v1/workorders/${encodeURIComponent(workorderId)}/assign`, jsonOptions('POST', input)),
  startWorkorder: (workorderId: string, input: { actor_user_id?: string; note?: string } = {}) => request<RemoteWorkorder>(`/v1/workorders/${encodeURIComponent(workorderId)}/start`, jsonOptions('POST', input)),
  submitWorkorderFeedback: (workorderId: string, input: { actor_user_id?: string; note: string; evidence?: Array<{ artifact_id: string; title?: string; content?: string }> }) => request<RemoteWorkorder>(`/v1/workorders/${encodeURIComponent(workorderId)}/feedback`, jsonOptions('POST', input)),
  reviewWorkorder: (workorderId: string, input: { reviewer_user_id?: string; decision: 'approved' | 'rejected'; comment: string; evidence_note?: string }) => request<RemoteWorkorder>(`/v1/workorders/${encodeURIComponent(workorderId)}/review`, jsonOptions('POST', input)),
  eventStreamUrl: (jobId: string, lastEventId = 0) => `${BASE_URL}/v1/jobs/${encodeURIComponent(jobId)}/events/stream?last_event_id=${lastEventId}`,
}
