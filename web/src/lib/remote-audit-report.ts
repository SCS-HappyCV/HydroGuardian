import type { RemoteAgentEvent, RemoteAgentJob, RemoteAgentStep, RemoteArtifactRecord, RemoteTaskRecord } from './remote-agent-types'
import type { RemoteWorkorder } from './remote-workorder-types'

export interface RemoteAuditReport {
  schema_version: 'hydro-audit-report.v1'
  generated_at: string
  subject: {
    job_id: string
    task_id?: string | null
    request_id: string
    trace_id: string
    status: string
  }
  task?: RemoteTaskRecord | null
  job: RemoteAgentJob
  execution: {
    plan?: Record<string, unknown> | null
    steps: RemoteAgentStep[]
    events: RemoteAgentEvent[]
  }
  findings: {
    risk_candidates: Array<Record<string, unknown>>
    quality?: Record<string, unknown> | null
    spatial_context?: Record<string, unknown> | null
    terminal_artifacts: Record<string, string>
  }
  artifacts: RemoteArtifactRecord[]
  workorders: RemoteWorkorder[]
  integrity: {
    algorithm: 'SHA-256'
    digest: string
    scope: string
    artifact_count: number
    event_count: number
  }
}
