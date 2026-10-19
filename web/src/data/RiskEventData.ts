// 风险事件数据模型：统一本地预置风险、智能体风险卡和可视化叠加层的前端字段。

import type {
  AgentVisualizationBBoxPixelData,
  AgentVisualizationPointData,
} from '@/lib/api-contracts'
import type { SpatialLocationData } from '@/lib/spatial-location'

export interface RiskEventData {
  id: string
  taskId: string
  zoneId: string
  ruleId: string
  templateId: string
  workorderId?: string
  title: string
  description: string
  level: 'high' | 'medium' | 'low' | 'review_required'
  score: number
  status: 'new' | 'review_required' | 'linked' | 'closed'
  evidenceSummary: string
  triggeredAt: string
  updatedAt: string
  caseId?: string
  candidateRegionId?: string
  riskCardId?: string
  overlayId?: string
  riskType?: string
  candidateScore?: number
  support?: number
  pointCount?: number
  overlayColor?: string
  bboxPixel?: AgentVisualizationBBoxPixelData
  polygonPixel?: AgentVisualizationPointData[]
  location?: SpatialLocationData
  evidenceRefs?: string[]
  reviewRequired?: boolean
  sourceTool?: string
  scoreKind?: string
  qualityGate?: {
    status: 'passed' | 'review_required'
    verdict: string
    score?: number
    abstentionRecommended: boolean
    automationAllowed: boolean
    reasons: string[]
  }
}

export type RiskEventFilterKey = keyof Pick<RiskEventData, 'taskId' | 'zoneId' | 'ruleId' | 'templateId' | 'level' | 'status'>
