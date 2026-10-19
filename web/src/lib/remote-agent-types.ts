export type RemoteJobStatus = 'queued_planning' | 'planning' | 'queued_execution' | 'executing' | 'succeeded' | 'blocked_expert' | 'failed' | 'cancelled'
export type RemoteStepStatus = 'pending' | 'dispatched' | 'running' | 'succeeded' | 'failed' | 'lost' | 'cancelled'

export interface RemoteAgentHealth { status: string; queue: Record<string, number> }
export interface RemoteAgentWorker { worker_id: string; version: string; capabilities: string[]; gpus: Array<Record<string, unknown>>; connected_at: number; last_heartbeat: number; pending_tasks: string[] }
export interface RemoteAgentJob {
  job_id: string
  request_id: string
  trace_id: string
  status: RemoteJobStatus
  submission: { request_id: string; query: string; language: string; assets: Record<string, string>; planned_request?: Record<string, unknown> | null }
  plan?: Record<string, unknown> | null
  result?: Record<string, unknown> | null
  error?: Record<string, unknown> | null
  attempts: number
  lease_owner?: string | null
  lease_expires_at?: number | null
  created_at: string
  updated_at: string
  version: number
}
export interface RemoteAgentStep { step_id: string; job_id: string; tool: string; status: RemoteStepStatus; attempt: number; worker_id?: string | null; progress: number; phase: string; arguments: Record<string, unknown>; result?: Record<string, unknown> | null; error?: Record<string, unknown> | null; updated_at: string }
export interface RemoteAgentEvent { event_id: number; event_type: string; from_status?: string | null; to_status?: string | null; payload?: Record<string, unknown>; created_at: string }
export interface RemoteAgentMessage { message_id: string; job_id: string; role: 'user' | 'assistant' | 'system'; intent: 'ask' | 'append_context' | 'workflow_patch' | 'replan' | 'cancel' | 'status'; content: string; metadata: Record<string, unknown>; created_at: string }
export interface RemoteChatRequest { request_id: string; job_id: string; message_id: string; status: 'queued' | 'running' | 'succeeded' | 'failed'; created_at: string; updated_at: string }
export interface RemoteMessageListResponse { job_id: string; messages: RemoteAgentMessage[]; count: number; pending: boolean; pending_requests: RemoteChatRequest[] }
export interface RemoteMessageResponse { job_id: string; messages: RemoteAgentMessage[]; job: RemoteAgentJob; pending: boolean; chat_request_id?: string | null; workflow_patch?: Record<string, unknown> }
export interface RemoteInterventionResponse { action: 'cancel' | 'replan'; job: RemoteAgentJob; previous_job?: RemoteAgentJob; task?: RemoteTaskRecord | null; messages: RemoteAgentMessage[] }
export interface RemoteArtifactRecord { artifact_id: string; bucket: string; object_key: string; media_type?: string | null; size_bytes?: number | null; sha256?: string | null; metadata?: Record<string, unknown> }
export interface RemoteTaskMetadata { task_id: string; name?: string; input_text: string; template_id?: string; zone_id?: string; scene_id?: string; sample_id?: string; priority?: 'low' | 'medium' | 'high'; created_by_user_id?: string; metadata?: Record<string, unknown> }
export interface RemoteJobSubmission { request_id: string; query: string; language?: string; assets: Record<string, string>; planned_request?: Record<string, unknown>; task?: RemoteTaskMetadata }
export interface RemotePresignResult { artifact: RemoteArtifactRecord; artifact_uri: string; upload_url: string }

export interface RemoteTaskRecord {
  task_id: string
  job_id: string
  request_id: string
  name: string
  input_text: string
  template_id?: string | null
  zone_id?: string | null
  scene_id?: string | null
  sample_id?: string | null
  priority: 'low' | 'medium' | 'high'
  created_by_user_id?: string | null
  metadata: Record<string, unknown>
  job_status: RemoteJobStatus
  status: 'queued' | 'running' | 'success' | 'failed'
  progress: number
  risk_count: number
  workorder_count: number
  artifact_count: number
  step_count: number
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  updated_at: string
}
