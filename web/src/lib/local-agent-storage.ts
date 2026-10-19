import type { AgentDemoSession, AgentPresentationSnapshot } from '@/lib/agent-presentation-types'

const SESSION_STORAGE_KEY = 'hydroguardian_agent_demo_sessions'
const SNAPSHOT_STORAGE_KEY = 'hydroguardian_agent_presentation_snapshots'

interface StoredSessions {
  version: 1
  items: Record<string, AgentDemoSession>
}

interface StoredSnapshots {
  version: 1
  items: Record<string, AgentPresentationSnapshot>
}

const EMPTY_SESSIONS: StoredSessions = { version: 1, items: {} }
const EMPTY_SNAPSHOTS: StoredSnapshots = { version: 1, items: {} }

function getStorage(): Storage | null {
  return typeof window === 'undefined' ? null : window.localStorage
}

function readValue<T extends { version: 1 }>(key: string, fallback: T): T {
  const storage = getStorage()
  if (!storage) return fallback

  const raw = storage.getItem(key)
  if (!raw) return fallback

  try {
    const parsed = JSON.parse(raw) as Partial<T>
    return parsed.version === 1 ? parsed as T : fallback
  } catch {
    return fallback
  }
}

function writeValue<T>(key: string, value: T): void {
  const storage = getStorage()
  if (!storage) return

  try {
    storage.setItem(key, JSON.stringify(value))
  } catch {
    // 存储不可用时保持当前页面可运行，下一次读取将回退到场景初始状态。
  }
}

export function getAgentDemoSessions(): Record<string, AgentDemoSession> {
  return readValue(SESSION_STORAGE_KEY, EMPTY_SESSIONS).items ?? {}
}

export function getAgentDemoSession(taskId: string): AgentDemoSession | undefined {
  return getAgentDemoSessions()[taskId]
}

export function saveAgentDemoSession(session: AgentDemoSession): void {
  const items = { ...getAgentDemoSessions(), [session.taskId]: session }
  writeValue(SESSION_STORAGE_KEY, { version: 1, items } satisfies StoredSessions)
}

export function getAgentPresentationSnapshots(): Record<string, AgentPresentationSnapshot> {
  return readValue(SNAPSHOT_STORAGE_KEY, EMPTY_SNAPSHOTS).items ?? {}
}

export function getAgentPresentationSnapshot(taskId: string): AgentPresentationSnapshot | undefined {
  return getAgentPresentationSnapshots()[taskId]
}

export function saveAgentPresentationSnapshot(snapshot: AgentPresentationSnapshot): void {
  const taskId = snapshot.task.taskId
  const items = { ...getAgentPresentationSnapshots(), [taskId]: snapshot }
  writeValue(SNAPSHOT_STORAGE_KEY, { version: 1, items } satisfies StoredSnapshots)
}

export function removeAgentDemoTask(taskId: string): void {
  const sessions = { ...getAgentDemoSessions() }
  const snapshots = { ...getAgentPresentationSnapshots() }
  delete sessions[taskId]
  delete snapshots[taskId]
  writeValue(SESSION_STORAGE_KEY, { version: 1, items: sessions } satisfies StoredSessions)
  writeValue(SNAPSHOT_STORAGE_KEY, { version: 1, items: snapshots } satisfies StoredSnapshots)
}

export function removeAgentDemoScenario(scenarioId: string): string[] {
  const sessions = { ...getAgentDemoSessions() }
  const snapshots = { ...getAgentPresentationSnapshots() }
  const removedTaskIds = Object.values(sessions)
    .filter((session) => session.scenarioId === scenarioId)
    .map((session) => session.taskId)

  removedTaskIds.forEach((taskId) => {
    delete sessions[taskId]
    delete snapshots[taskId]
  })

  writeValue(SESSION_STORAGE_KEY, { version: 1, items: sessions } satisfies StoredSessions)
  writeValue(SNAPSHOT_STORAGE_KEY, { version: 1, items: snapshots } satisfies StoredSnapshots)
  return removedTaskIds
}

export function resetAgentDemoStorage(): void {
  const storage = getStorage()
  if (!storage) return
  storage.removeItem(SESSION_STORAGE_KEY)
  storage.removeItem(SNAPSHOT_STORAGE_KEY)
}
