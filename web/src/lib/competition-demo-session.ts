import { competitionDemo } from '@/data/CompetitionDemoData'

export type CompetitionDemoStage = 'studio' | 'execution' | 'risk' | 'workorder' | 'review' | 'replay'

export interface CompetitionDemoSession {
  version: 1
  active: boolean
  stage: CompetitionDemoStage
  startedAt: string
  updatedAt: string
}

export const competitionDemoStages = [
  { id: 'studio', label: '任务理解', value: '理解自然语言目标', icon: 'MessageSquareText', href: `./task-studio.html?taskId=${competitionDemo.taskId}&sceneId=${competitionDemo.sceneId}` },
  { id: 'execution', label: '动态执行', value: '规划并调用专家能力', icon: 'Network', href: `./task-execution-monitor.html?taskId=${competitionDemo.taskId}` },
  { id: 'risk', label: '风险研判', value: '融合证据与质量验证', icon: 'ScanSearch', href: `./risk-workspace.html?taskId=${competitionDemo.taskId}&riskId=risk-agent-001` },
  { id: 'workorder', label: '现场处置', value: '承接建议与现场反馈', icon: 'HardHat', href: `./workorder-detail.html?orderId=wo-agent-draft-001` },
  { id: 'review', label: '人工复核', value: '确认结果并安全闭环', icon: 'UserRoundCheck', href: `./workorder-review.html?orderId=wo-agent-draft-001` },
  { id: 'replay', label: '案例复盘', value: '回看完整决策链路', icon: 'History', href: './history.html' },
] as const

const STORAGE_KEY = 'hydroguardian_competition_demo_session_v1'

export function startCompetitionDemoSession(): CompetitionDemoSession {
  const now = new Date().toISOString()
  const session: CompetitionDemoSession = { version: 1, active: true, stage: 'studio', startedAt: now, updatedAt: now }
  saveCompetitionDemoSession(session)
  return session
}

export function getCompetitionDemoSession(): CompetitionDemoSession | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try { return JSON.parse(raw) as CompetitionDemoSession } catch { return null }
}

export function updateCompetitionDemoStage(stage: CompetitionDemoStage): CompetitionDemoSession | null {
  const current = getCompetitionDemoSession()
  if (!current?.active) return null
  const next = { ...current, stage, updatedAt: new Date().toISOString() }
  saveCompetitionDemoSession(next)
  return next
}

export function clearCompetitionDemoSession(): void {
  if (typeof localStorage !== 'undefined') localStorage.removeItem(STORAGE_KEY)
}

function saveCompetitionDemoSession(session: CompetitionDemoSession): void {
  if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
}

export function resolveCompetitionDemoStage(path: string): CompetitionDemoStage | null {
  if (path.includes('task-studio')) return 'studio'
  if (path.includes('task-execution')) return 'execution'
  if (path.includes('risk-workspace')) return 'risk'
  if (path.includes('workorder-review')) return 'review'
  if (path.includes('workorder-detail')) return 'workorder'
  if (path.includes('history')) return 'replay'
  return null
}
