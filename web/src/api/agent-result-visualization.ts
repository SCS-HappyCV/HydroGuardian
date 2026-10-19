// 智能体可视化结果转换层：将后端 agent-result 快照映射为风险工作台可直接消费的数据。

import type {
  AgentResultSnapshotData,
  AgentRiskOverlayData,
} from '@/lib/api-contracts'
import type { RiskEventData } from '@/data/RiskEventData'

type RiskLevel = RiskEventData['level']
type RiskStatus = RiskEventData['status']

export interface AgentRiskBuildContext {
  fallbackTaskId?: string | null
  fallbackZoneId?: string | null
}

// 将后端风险等级规整为前端徽标支持的等级集合。
export function normalizeAgentRiskLevel(level?: string | null, reviewRequired?: boolean): RiskLevel {
  const normalized = (level || '').trim().toLowerCase()

  if (reviewRequired || normalized.includes('review')) return 'review_required'
  if (['high', 'critical', 'severe', '高', '高风险'].includes(normalized)) return 'high'
  if (['medium', 'middle', 'moderate', '中', '中风险'].includes(normalized)) return 'medium'
  if (['low', 'minor', '轻微', '低', '低风险'].includes(normalized)) return 'low'

  return 'review_required'
}

// 将任意数字分数转换为 0-100 的整数分，兼容后端 0-1 概率和 0-100 分值。
export function normalizeRiskScore(score?: number | null): number {
  if (typeof score !== 'number' || Number.isNaN(score)) return 0
  const normalized = score <= 1 ? score * 100 : score
  return Math.max(0, Math.min(100, Math.round(normalized)))
}

// 根据后端复核标记推导前端风险处理状态。
function buildRiskStatus(overlay: AgentRiskOverlayData): RiskStatus {
  return overlay.reviewRequired ? 'review_required' : 'new'
}

// 生成稳定风险 ID，保证地图、表格和详情卡可以联动同一个对象。
function buildRiskId(overlay: AgentRiskOverlayData, index: number): string {
  return overlay.riskCardId || overlay.overlayId || overlay.regionId || `agent-risk-${index + 1}`
}

// 汇总 EvidencePack 文本，优先使用后端证据摘要，再补充叠加层自身摘要。
function buildEvidenceSummary(agentResult: AgentResultSnapshotData, overlay: AgentRiskOverlayData): string {
  const summary = agentResult.visualization?.evidenceMetrics?.evidenceSummary || []
  const parts = [...summary, overlay.summary].filter((item): item is string => Boolean(item && item.trim()))

  if (parts.length > 0) {
    return parts.join('；')
  }

  return '智能体已生成疑似风险区域，建议结合正射图叠加结果复核。'
}

// 将单个后端风险叠加层转换为前端风险事件。
function overlayToRiskEvent(
  agentResult: AgentResultSnapshotData,
  overlay: AgentRiskOverlayData,
  index: number,
  context: AgentRiskBuildContext,
): RiskEventData {
  const createdAt = agentResult.caseCreatedAt || agentResult.case?.createdAt || new Date().toISOString()
  const riskId = buildRiskId(overlay, index)
  const score = normalizeRiskScore(overlay.riskScore ?? overlay.candidateScore)
  const level = normalizeAgentRiskLevel(overlay.riskLevel, overlay.reviewRequired)

  return {
    id: riskId,
    taskId: context.fallbackTaskId || agentResult.taskId || agentResult.caseId || 'agent-result',
    zoneId: context.fallbackZoneId || agentResult.sceneId || agentResult.visualization?.sceneId || 'agent-scene',
    ruleId: overlay.riskType || 'agent-risk-rule',
    templateId: overlay.regionId || overlay.overlayId || 'agent-visual-template',
    title: overlay.label || overlay.riskType || `疑似风险区域 ${index + 1}`,
    description: overlay.summary || `${overlay.riskType || '智能体'} 识别到疑似风险区域。`,
    level,
    score,
    status: buildRiskStatus(overlay),
    evidenceSummary: buildEvidenceSummary(agentResult, overlay),
    triggeredAt: createdAt,
    updatedAt: createdAt,
    caseId: agentResult.caseId || agentResult.case?.caseId,
    candidateRegionId: overlay.regionId,
    riskCardId: overlay.riskCardId,
    overlayId: overlay.overlayId,
    riskType: overlay.riskType,
    candidateScore: normalizeRiskScore(overlay.candidateScore),
    support: overlay.support,
    pointCount: overlay.pointCount,
    overlayColor: overlay.color,
    bboxPixel: overlay.bboxPixel,
    polygonPixel: overlay.polygonPixel,
  }
}

// 从完整 agent-result 快照提取风险工作台列表；无可视化叠加层时返回空数组交给页面兜底。
export function buildRisksFromAgentResult(
  agentResult: AgentResultSnapshotData | null | undefined,
  context: AgentRiskBuildContext = {},
): RiskEventData[] {
  const overlays = agentResult?.visualization?.riskOverlays || []

  return overlays.map((overlay, index) => overlayToRiskEvent(agentResult!, overlay, index, context))
}
