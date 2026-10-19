import type { AgentPresentationSnapshot } from '@/lib/agent-presentation-types'

export interface RemoteAgentTaskBinding { taskId: string; jobId: string; requestId: string; taskText: string; sceneId: string; createdAt: string }
const STORAGE_KEY = 'hydroguardian_remote_agent_bindings_v1'
const SNAPSHOT_STORAGE_KEY = 'hydroguardian_remote_agent_snapshots_v1'

export function getRemoteAgentBinding(taskId: string): RemoteAgentTaskBinding | undefined {
  return getBindings()[taskId]
}
export function saveRemoteAgentBinding(binding: RemoteAgentTaskBinding): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...getBindings(), [binding.taskId]: binding }))
  } catch {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ [binding.taskId]: binding })) } catch {}
  }
}
export function getRemoteAgentSnapshot(taskId: string): AgentPresentationSnapshot | undefined {
  if (typeof localStorage === 'undefined') return undefined
  const raw = localStorage.getItem(SNAPSHOT_STORAGE_KEY)
  if (!raw) return undefined
  try { return (JSON.parse(raw) as Record<string, AgentPresentationSnapshot>)[taskId] } catch { return undefined }
}
export function getRemoteAgentSnapshots(): AgentPresentationSnapshot[] {
  if (typeof localStorage === 'undefined') return []
  const raw = localStorage.getItem(SNAPSHOT_STORAGE_KEY)
  if (!raw) return []
  try { return Object.values(JSON.parse(raw) as Record<string, AgentPresentationSnapshot>) } catch { return [] }
}
export function saveRemoteAgentSnapshot(snapshot: AgentPresentationSnapshot): void {
  if (typeof localStorage === 'undefined') return
  let snapshots: Record<string, AgentPresentationSnapshot> = {}
  try { snapshots = JSON.parse(localStorage.getItem(SNAPSHOT_STORAGE_KEY) || '{}') as Record<string, AgentPresentationSnapshot> } catch { snapshots = {} }
  const persistent = JSON.parse(JSON.stringify(snapshot)) as AgentPresentationSnapshot
  persistent.evidence.artifacts.forEach((artifact) => {
    delete artifact.previewUrl
    delete artifact.downloadUrl
  })
  try {
    localStorage.setItem(SNAPSHOT_STORAGE_KEY, JSON.stringify({ ...snapshots, [snapshot.task.taskId]: persistent }))
  } catch {
    try { localStorage.setItem(SNAPSHOT_STORAGE_KEY, JSON.stringify({ [snapshot.task.taskId]: persistent })) } catch {}
  }
}
function getBindings(): Record<string, RemoteAgentTaskBinding> {
  if (typeof localStorage === 'undefined') return {}
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return {}
  try { return JSON.parse(raw) as Record<string, RemoteAgentTaskBinding> } catch { return {} }
}
