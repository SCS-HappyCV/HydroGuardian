import { remoteAgentApi } from '@/api/remote-agent-api'
import { mapRemoteAgentEvent, mapRemoteAgentSnapshot } from '@/lib/remote-agent-mapper'
import { adaptRemoteAgentResult } from '@/lib/remote-agent-result-adapter'
import { getRemoteAgentBinding, getRemoteAgentSnapshot, saveRemoteAgentBinding, saveRemoteAgentSnapshot, type RemoteAgentTaskBinding } from '@/lib/remote-agent-storage'
import type { AgentPresentationSnapshot } from '@/lib/agent-presentation-types'
import type { RemoteAgentEvent, RemoteAgentWorker, RemoteJobSubmission, RemoteTaskMetadata } from '@/lib/remote-agent-types'

type Listener = (snapshot: AgentPresentationSnapshot) => void
export type RemoteStreamState = 'connecting' | 'connected' | 'reconnecting' | 'polling' | 'closed'
type StreamListener = (state: RemoteStreamState) => void
const TERMINAL = new Set(['succeeded', 'blocked_expert', 'failed', 'cancelled'])

export class RemoteAgentProvider {
  private streams = new Map<string, EventSource>()
  private listeners = new Map<string, Set<Listener>>()
  private pollers = new Map<string, ReturnType<typeof setInterval>>()
  private reconnectTimers = new Map<string, ReturnType<typeof setTimeout>>()
  private refreshes = new Map<string, Promise<void>>()
  private streamListeners = new Map<string, Set<StreamListener>>()
  private lastEventIds = new Map<string, number>()

  async createTask(input: { taskId: string; taskText: string; sceneId: string; assets: Record<string, string>; plannedRequest?: Record<string, unknown>; metadata?: Omit<RemoteTaskMetadata, 'task_id' | 'input_text' | 'scene_id'> }): Promise<AgentPresentationSnapshot> {
    const requestId = `web-${input.taskId}-${Date.now()}`
    const plannedRequest = input.plannedRequest ? { ...input.plannedRequest, request_id: requestId } : undefined
    const submission: RemoteJobSubmission = { request_id: requestId, query: input.taskText, language: 'zh', assets: input.assets, planned_request: plannedRequest, task: { task_id: input.taskId, input_text: input.taskText, scene_id: input.sceneId, ...input.metadata } }
    const job = await remoteAgentApi.createJob(submission, requestId)
    const binding: RemoteAgentTaskBinding = { taskId: input.taskId, jobId: job.job_id, requestId, taskText: input.taskText, sceneId: input.sceneId, createdAt: job.created_at }
    saveRemoteAgentBinding(binding)
    return this.refresh(input.taskId)
  }

  async restore(taskId: string) { return getRemoteAgentBinding(taskId) ? this.refresh(taskId) : undefined }
  async refresh(taskId: string): Promise<AgentPresentationSnapshot> {
    const binding = getRemoteAgentBinding(taskId)
    if (!binding) throw new Error('未找到真实 Agent 任务关联')
    const [job, steps, events, artifacts, workers] = await Promise.all([remoteAgentApi.getJob(binding.jobId), remoteAgentApi.getSteps(binding.jobId), remoteAgentApi.getEvents(binding.jobId), remoteAgentApi.getArtifacts(binding.jobId), remoteAgentApi.workers().catch((): RemoteAgentWorker[] => [])])
    const latestEventId = events.reduce((latest, event) => Math.max(latest, event.event_id), 0)
    if (latestEventId) this.lastEventIds.set(taskId, latestEventId)
    const adaptedResult = await adaptRemoteAgentResult({ job, steps, terminalArtifacts: artifacts })
    const snapshot = mapRemoteAgentSnapshot({ binding, job, steps, events, artifacts, adaptedResult, workers })
    saveRemoteAgentSnapshot(snapshot)
    return snapshot
  }
  async cancel(taskId: string) { const binding = getRemoteAgentBinding(taskId); if (!binding) return; await remoteAgentApi.cancelJob(binding.jobId); return this.refresh(taskId) }
  async retry(taskId: string) { const binding = getRemoteAgentBinding(taskId); if (!binding) return; await remoteAgentApi.retryJob(binding.jobId); return this.refresh(taskId) }
  subscribe(taskId: string, listener: Listener, streamListener?: StreamListener): () => void {
    const binding = getRemoteAgentBinding(taskId)
    if (!binding || typeof EventSource === 'undefined') return () => undefined
    const listeners = this.listeners.get(taskId) || new Set<Listener>(); listeners.add(listener); this.listeners.set(taskId, listeners)
    if (streamListener) { const streamListeners = this.streamListeners.get(taskId) || new Set<StreamListener>(); streamListeners.add(streamListener); this.streamListeners.set(taskId, streamListeners) }
    this.connect(taskId, binding)
    if (!this.pollers.has(taskId)) this.pollers.set(taskId, setInterval(() => { void this.publish(taskId) }, 4000))
    return () => { this.listeners.get(taskId)?.delete(listener); if (streamListener) this.streamListeners.get(taskId)?.delete(streamListener); if (!this.listeners.get(taskId)?.size) this.close(taskId) }
  }

  private setStreamState(taskId: string, state: RemoteStreamState) { this.streamListeners.get(taskId)?.forEach((listener) => listener(state)) }

  private handleStreamEvent(taskId: string, raw: MessageEvent) {
    try {
      const event = JSON.parse(raw.data) as RemoteAgentEvent
      if (!event?.event_id) return
      this.lastEventIds.set(taskId, Math.max(this.lastEventIds.get(taskId) || 0, event.event_id))
      const cached = getRemoteAgentSnapshot(taskId)
      if (cached && !cached.trace.some((item) => item.traceId === String(event.event_id))) {
        const snapshot = { ...cached, trace: [...cached.trace, mapRemoteAgentEvent(event)] }
        saveRemoteAgentSnapshot(snapshot)
        this.listeners.get(taskId)?.forEach((listener) => listener(snapshot))
      }
      void this.publish(taskId)
    } catch { void this.publish(taskId) }
  }

  private connect(taskId: string, binding: RemoteAgentTaskBinding) {
    if (this.streams.has(taskId) || !this.listeners.get(taskId)?.size) return
    this.setStreamState(taskId, 'connecting')
    const source = new EventSource(remoteAgentApi.eventStreamUrl(binding.jobId, this.lastEventIds.get(taskId) || 0))
    source.onopen = () => this.setStreamState(taskId, 'connected')
    source.addEventListener('job', (event) => this.handleStreamEvent(taskId, event as MessageEvent))
    source.onmessage = (event) => this.handleStreamEvent(taskId, event)
    source.onerror = () => {
      source.close()
      this.streams.delete(taskId)
      this.setStreamState(taskId, 'reconnecting')
      if (!this.listeners.get(taskId)?.size || this.reconnectTimers.has(taskId)) return
      this.reconnectTimers.set(taskId, setTimeout(() => {
        this.reconnectTimers.delete(taskId)
        this.connect(taskId, binding)
      }, 2000))
    }
    this.streams.set(taskId, source)
  }

  private publish(taskId: string): Promise<void> {
    const active = this.refreshes.get(taskId)
    if (active) return active
    const request = (async () => {
      try {
        const snapshot = await this.refresh(taskId)
        this.listeners.get(taskId)?.forEach((item) => item(snapshot))
        const binding = getRemoteAgentBinding(taskId)
        if (binding && TERMINAL.has((await remoteAgentApi.getJob(binding.jobId)).status)) this.close(taskId)
      } catch {}
      finally { this.refreshes.delete(taskId) }
    })()
    this.refreshes.set(taskId, request)
    return request
  }

  close(taskId: string) {
    this.streams.get(taskId)?.close()
    this.streams.delete(taskId)
    const poller = this.pollers.get(taskId)
    if (poller) clearInterval(poller)
    this.pollers.delete(taskId)
    const reconnectTimer = this.reconnectTimers.get(taskId)
    if (reconnectTimer) clearTimeout(reconnectTimer)
    this.reconnectTimers.delete(taskId)
    this.setStreamState(taskId, 'closed')
    this.streamListeners.delete(taskId)
    this.listeners.delete(taskId)
  }
}

export const remoteAgentProvider = new RemoteAgentProvider()
