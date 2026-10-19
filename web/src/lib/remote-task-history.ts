import type { TaskData } from '@/data/TaskData'
import type { RemoteTaskRecord } from './remote-agent-types'
import { saveRemoteAgentBinding } from './remote-agent-storage'

export function mapRemoteTask(task: RemoteTaskRecord): TaskData {
  return {
    id: task.task_id,
    name: task.name,
    inputText: task.input_text,
    templateId: task.template_id || 'custom',
    zoneId: task.zone_id || 'agent-analysis-zone',
    sampleId: task.sample_id || undefined,
    priority: task.priority,
    status: task.status,
    progress: task.progress,
    createdAt: task.created_at,
    startedAt: task.started_at || undefined,
    finishedAt: task.finished_at || undefined,
    createdByUserId: task.created_by_user_id || 'user-001',
    updatedAt: task.updated_at,
    remoteJobId: task.job_id,
    riskCount: task.risk_count,
    workorderCount: task.workorder_count,
    artifactCount: task.artifact_count,
    stepCount: task.step_count,
  }
}

export function restoreRemoteTaskBinding(task: RemoteTaskRecord): void {
  saveRemoteAgentBinding({
    taskId: task.task_id,
    jobId: task.job_id,
    requestId: task.request_id,
    taskText: task.input_text,
    sceneId: task.scene_id || task.zone_id || 'remote-scene',
    createdAt: task.created_at,
  })
}
