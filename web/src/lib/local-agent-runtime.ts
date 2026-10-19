import { getAgentDemoScenario } from '@/data/agent-demo/scenarios'
import { matchAgentDemoScenario } from '@/lib/agent-scenario-matcher'
import {
  getAgentDemoSession,
  getAgentDemoSessions,
  getAgentPresentationSnapshot,
  removeAgentDemoScenario,
  removeAgentDemoTask,
  saveAgentDemoSession,
  saveAgentPresentationSnapshot,
} from '@/lib/local-agent-storage'
import type {
  AgentDemoScenario,
  AgentDemoSession,
  AgentExecutionStatus,
  AgentPresentationProvider,
  AgentPresentationSnapshot,
  AgentTaskInput,
} from '@/lib/agent-presentation-types'

type SnapshotListener = (snapshot: AgentPresentationSnapshot) => void

const TERMINAL_STATUSES: AgentExecutionStatus[] = [
  'completed',
  'review_required',
  'clarification_required',
  'abstained',
  'blocked',
  'cancelled',
  'failed',
]

function isTerminalStatus(status: AgentExecutionStatus): boolean {
  return TERMINAL_STATUSES.includes(status)
}

function cloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function materializeSnapshot(
  scenario: AgentDemoScenario,
  session: AgentDemoSession,
): AgentPresentationSnapshot {
  const timelineItem = scenario.timeline[session.currentStep] ?? scenario.timeline[0]
  const snapshot = cloneValue(timelineItem.snapshot)
  const now = new Date().toISOString()

  snapshot.snapshotId = `${session.taskId}-snapshot-${snapshot.sequence}`
  snapshot.task.taskId = session.taskId
  snapshot.task.taskText = session.taskInput.taskText || snapshot.task.taskText
  snapshot.task.sceneId = session.taskInput.sceneId ?? snapshot.task.sceneId
  snapshot.task.sampleId = session.taskInput.sampleId ?? snapshot.task.sampleId
  if (session.status === 'paused') snapshot.status = 'paused'
  snapshot.createdAt = now
  snapshot.trace = snapshot.trace.map((item) => ({ ...item, timestamp: now }))
  return snapshot
}

export class LocalAgentRuntime implements AgentPresentationProvider {
  private timers = new Map<string, ReturnType<typeof setTimeout>>()
  private listeners = new Map<string, Set<SnapshotListener>>()

  async createTask(input: AgentTaskInput): Promise<AgentPresentationSnapshot> {
    const scenario = matchAgentDemoScenario(input)
    const firstSnapshot = scenario.timeline[0].snapshot
    const now = new Date().toISOString()
    const session: AgentDemoSession = {
      version: 1,
      scenarioId: scenario.scenarioId,
      taskId: input.taskId || firstSnapshot.task.taskId,
      taskInput: { ...input, scenarioId: scenario.scenarioId },
      currentStep: 0,
      status: firstSnapshot.status,
      playbackRate: 1,
      updatedAt: now,
    }

    this.clearTimer(session.taskId)
    removeAgentDemoTask(session.taskId)
    saveAgentDemoSession(session)
    return this.persistAndEmit(scenario, session)
  }

  getSnapshot(taskId: string): AgentPresentationSnapshot | undefined {
    return getAgentPresentationSnapshot(taskId)
  }

  getSession(taskId: string): AgentDemoSession | undefined {
    return getAgentDemoSession(taskId)
  }

  getSessions(): AgentDemoSession[] {
    return Object.values(getAgentDemoSessions())
  }

  start(taskId: string): AgentPresentationSnapshot | undefined {
    const context = this.getContext(taskId)
    if (!context) return undefined

    let { session } = context
    if (isTerminalStatus(context.snapshot.status)) {
      session = { ...session, currentStep: 0 }
    }

    const now = new Date().toISOString()
    session = {
      ...session,
      status: 'running',
      startedAt: now,
      updatedAt: now,
    }
    saveAgentDemoSession(session)
    const snapshot = this.persistAndEmit(context.scenario, session)
    this.scheduleNext(context.scenario, session)
    return snapshot
  }

  pause(taskId: string): AgentPresentationSnapshot | undefined {
    const context = this.getContext(taskId)
    if (!context) return undefined
    this.clearTimer(taskId)

    const session: AgentDemoSession = {
      ...context.session,
      status: 'paused',
      updatedAt: new Date().toISOString(),
    }
    saveAgentDemoSession(session)
    return this.persistAndEmit(context.scenario, session)
  }

  resume(taskId: string): AgentPresentationSnapshot | undefined {
    const context = this.getContext(taskId)
    if (!context || context.session.status !== 'paused') return context?.snapshot

    const session: AgentDemoSession = {
      ...context.session,
      status: 'running',
      updatedAt: new Date().toISOString(),
    }
    saveAgentDemoSession(session)
    const snapshot = this.persistAndEmit(context.scenario, session)
    this.scheduleNext(context.scenario, session)
    return snapshot
  }

  advance(taskId: string): AgentPresentationSnapshot | undefined {
    const context = this.getContext(taskId)
    if (!context) return undefined

    this.clearTimer(taskId)
    const lastStep = context.scenario.timeline.length - 1
    const nextStep = Math.min(context.session.currentStep + 1, lastStep)
    const nextStatus = context.scenario.timeline[nextStep].snapshot.status
    const session: AgentDemoSession = {
      ...context.session,
      currentStep: nextStep,
      status: isTerminalStatus(nextStatus) ? nextStatus : 'running',
      updatedAt: new Date().toISOString(),
    }
    saveAgentDemoSession(session)
    const snapshot = this.persistAndEmit(context.scenario, session)

    if (!isTerminalStatus(snapshot.status) && nextStep < lastStep) {
      this.scheduleNext(context.scenario, session)
    }
    return snapshot
  }

  complete(taskId: string): AgentPresentationSnapshot | undefined {
    const context = this.getContext(taskId)
    if (!context) return undefined
    this.clearTimer(taskId)

    const lastStep = context.scenario.timeline.length - 1
    const finalStatus = context.scenario.timeline[lastStep].snapshot.status
    const session: AgentDemoSession = {
      ...context.session,
      currentStep: lastStep,
      status: finalStatus,
      updatedAt: new Date().toISOString(),
    }
    saveAgentDemoSession(session)
    return this.persistAndEmit(context.scenario, session)
  }

  setPlaybackRate(taskId: string, playbackRate: number): AgentPresentationSnapshot | undefined {
    const context = this.getContext(taskId)
    if (!context) return undefined

    const safeRate = Math.min(2, Math.max(0.5, playbackRate))
    const session: AgentDemoSession = {
      ...context.session,
      playbackRate: safeRate,
      updatedAt: new Date().toISOString(),
    }
    saveAgentDemoSession(session)

    if (session.status === 'running') this.scheduleNext(context.scenario, session)
    return this.persistAndEmit(context.scenario, session)
  }

  restore(taskId: string): AgentPresentationSnapshot | undefined {
    const context = this.getContext(taskId)
    if (!context) return undefined

    const snapshot = this.persistAndEmit(context.scenario, context.session)
    if (context.session.status === 'running' && !isTerminalStatus(snapshot.status)) {
      this.scheduleNext(context.scenario, context.session)
    }
    return snapshot
  }

  subscribe(taskId: string, listener: SnapshotListener): () => void {
    const taskListeners = this.listeners.get(taskId) ?? new Set<SnapshotListener>()
    taskListeners.add(listener)
    this.listeners.set(taskId, taskListeners)

    return () => {
      const currentListeners = this.listeners.get(taskId)
      currentListeners?.delete(listener)
      if (currentListeners?.size === 0) this.listeners.delete(taskId)
    }
  }

  resetScenario(scenarioId: string): void {
    const taskIds = removeAgentDemoScenario(scenarioId)
    taskIds.forEach((taskId) => {
      this.clearTimer(taskId)
      this.listeners.delete(taskId)
    })
  }

  destroy(): void {
    this.timers.forEach((timer) => clearTimeout(timer))
    this.timers.clear()
    this.listeners.clear()
  }

  private getContext(taskId: string): {
    scenario: AgentDemoScenario
    session: AgentDemoSession
    snapshot: AgentPresentationSnapshot
  } | undefined {
    const session = getAgentDemoSession(taskId)
    if (!session) return undefined
    const scenario = getAgentDemoScenario(session.scenarioId)
    if (!scenario) return undefined
    const snapshot = getAgentPresentationSnapshot(taskId) ?? materializeSnapshot(scenario, session)
    return { scenario, session, snapshot }
  }

  private persistAndEmit(
    scenario: AgentDemoScenario,
    session: AgentDemoSession,
  ): AgentPresentationSnapshot {
    const snapshot = materializeSnapshot(scenario, session)
    saveAgentPresentationSnapshot(snapshot)
    this.listeners.get(session.taskId)?.forEach((listener) => listener(snapshot))
    return snapshot
  }

  private scheduleNext(scenario: AgentDemoScenario, session: AgentDemoSession): void {
    this.clearTimer(session.taskId)
    if (session.status !== 'running') return

    const nextStep = session.currentStep + 1
    if (nextStep >= scenario.timeline.length) return

    const currentAt = scenario.timeline[session.currentStep]?.atMs ?? 0
    const nextAt = scenario.timeline[nextStep].atMs
    const delayMs = Math.max(100, (nextAt - currentAt) / session.playbackRate)
    const timer = setTimeout(() => this.advance(session.taskId), delayMs)
    this.timers.set(session.taskId, timer)
  }

  private clearTimer(taskId: string): void {
    const timer = this.timers.get(taskId)
    if (timer) clearTimeout(timer)
    this.timers.delete(taskId)
  }
}

export const localAgentRuntime = new LocalAgentRuntime()
