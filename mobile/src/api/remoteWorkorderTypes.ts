export type RemoteWorkorderStatus = 'todo' | 'doing' | 'review' | 'closed'

export interface RemoteWorkorderEvidence {
  evidence_id: string
  evidence_type: 'source' | 'after' | 'note'
  artifact_id?: string | null
  title: string
  content?: string | null
  media_type?: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface RemoteWorkorderReview {
  review_id: string
  reviewer_user_id?: string | null
  decision: 'approved' | 'rejected'
  comment: string
  evidence_note?: string | null
  created_at: string
}

export interface RemoteWorkorderTimeline {
  event_id: number
  actor_user_id?: string | null
  action: string
  from_status?: RemoteWorkorderStatus | null
  to_status?: RemoteWorkorderStatus | null
  note?: string | null
  payload: Record<string, unknown>
  created_at: string
}

export interface RemoteWorkorder {
  workorder_id: string
  job_id: string
  candidate_id: string
  region_id: string
  task_id?: string | null
  status: RemoteWorkorderStatus
  title: string
  summary: string
  risk_type: string
  risk_level: string
  score: number
  rule_id?: string | null
  recommendation?: string | null
  priority?: string | null
  assignee_user_id?: string | null
  reviewer_user_id?: string | null
  due_at?: string | null
  risk_snapshot: Record<string, unknown>
  created_at: string
  updated_at: string
  version: number
  evidence: RemoteWorkorderEvidence[]
  reviews: RemoteWorkorderReview[]
  timeline: RemoteWorkorderTimeline[]
}

export interface RemoteArtifact {
  artifact_id: string
  bucket: string
  object_key: string
  media_type?: string | null
  size_bytes?: number | null
  metadata?: Record<string, unknown>
}

export interface RemotePresignResult {
  artifact: RemoteArtifact
  artifact_uri: string
  upload_url: string
}
