export type MobileRiskLevel = 'high' | 'medium' | 'review_required'
export type MobileWorkOrderStatus = 'todo' | 'assigned' | 'in_progress' | 'reviewed' | 'closed'

export interface MobileEvidence {
  id: string
  type: 'image' | 'geometry' | 'change' | 'rule'
  title: string
  summary: string
  metric: string
  score: number
  artifactId?: string
  previewUrl?: string
  previewKind?: 'image' | 'dataset' | 'report'
  mediaType?: string
}

export interface MobileTimelineEvent {
  id: string
  label: string
  detail: string
  at: string
  state: 'done' | 'current' | 'pending'
}

export interface MobileWorkOrder {
  id: string
  caseId: string
  taskId: string
  riskId: string
  title: string
  area: string
  riskLevel: MobileRiskLevel
  status: MobileWorkOrderStatus
  deadline: string
  distanceMeters: number
  confidence: number
  uncertainty: number
  summary: string
  recommendedAction: string
  assignee: string
  reviewer: string
  longitude: number
  latitude: number
  evidence: MobileEvidence[]
  timeline: MobileTimelineEvent[]
  progress: number
  updatedAt: string
  source?: 'local' | 'remote'
  jobId?: string
  remoteVersion?: number
}

export const statusLabels: Record<MobileWorkOrderStatus, string> = {
  todo: '待接收',
  assigned: '已接收',
  in_progress: '处置中',
  reviewed: '待复核',
  closed: '已闭环',
}

export const riskLevelLabels: Record<MobileRiskLevel, string> = {
  high: '高风险',
  medium: '中风险',
  review_required: '待核验',
}
