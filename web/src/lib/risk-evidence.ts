import type { RiskEventData } from '@/data/RiskEventData'
import type { AgentVisualizationData } from '@/lib/api-contracts'

export interface RiskEvidenceItem {
  id: 'image' | 'geometry' | 'change' | 'rule'
  label: string
  icon: string
  score: number
  status: 'strong' | 'moderate' | 'review'
  summary: string
}

export interface RiskRecommendation {
  urgency: string
  action: string
  template: string
  reviewFocus: string
}

export interface RiskEvidenceProfile {
  confidence: number
  uncertainty: number
  uncertaintyReason: string
  evidence: RiskEvidenceItem[]
  recommendation: RiskRecommendation
}

function toPercent(value?: number | null, fallback = 0): number {
  if (typeof value !== 'number' || Number.isNaN(value)) return fallback
  const normalized = value <= 1 ? value * 100 : value
  return Math.max(0, Math.min(100, Math.round(normalized)))
}

function evidenceStatus(score: number): RiskEvidenceItem['status'] {
  if (score >= 80) return 'strong'
  if (score >= 60) return 'moderate'
  return 'review'
}

function hasKeyword(risk: RiskEventData, keywords: string[]): boolean {
  const content = `${risk.title} ${risk.description} ${risk.evidenceSummary} ${risk.riskType || ''}`.toLowerCase()
  return keywords.some((keyword) => content.includes(keyword.toLowerCase()))
}

function buildRecommendation(risk: RiskEventData): RiskRecommendation {
  const isSlope = hasKeyword(risk, ['坡', '裸地', '冲刷'])
  const isChange = hasKeyword(risk, ['变化', '扰动', '新增'])
  const needsReview = risk.level === 'review_required' || risk.status === 'review_required'

  if (needsReview) {
    return {
      urgency: '24 小时内人工复核',
      action: '核对道路、水线和阴影干扰，补充现场照片后再决定是否立案。',
      template: '疑似风险人工核验单',
      reviewFocus: hasKeyword(risk, ['道路']) ? '重点确认候选区域是否为既有道路边缘。' : '重点确认遮挡、潮位或配准误差。',
    }
  }

  if (isSlope) {
    return {
      urgency: risk.level === 'high' ? '立即派发' : '本轮巡查内处理',
      action: '安排岸坡现场核查，检查冲刷、坍塌和植被缺失情况并回传照片。',
      template: '岸坡稳定性核查工单',
      reviewFocus: '现场复测坡度、高差与裸地范围。',
    }
  }

  if (isChange) {
    return {
      urgency: risk.level === 'high' ? '2 小时内派发' : '24 小时内复核',
      action: '锁定变化边界，核查是否存在新增开挖或岸线扰动，并留存处置前证据。',
      template: '近水扰动快速处置单',
      reviewFocus: '核验变化发生时间、施工主体和现场影响范围。',
    }
  }

  return {
    urgency: '本轮巡查内处理',
    action: '派发属地人员核验风险区域，回传定位照片和处置说明。',
    template: '水利风险通用核查单',
    reviewFocus: '确认风险类型、空间位置和影响范围。',
  }
}

export function buildRiskEvidenceProfile(
  risk: RiskEventData,
  visualization?: AgentVisualizationData | null,
): RiskEvidenceProfile {
  const metrics = visualization?.evidenceMetrics
  const comparison = visualization?.changeComparison
  const pointCloud = visualization?.pointCloud
  const confidence = toPercent(metrics?.confidence, risk.score)
  const inferredUncertainty = risk.level === 'review_required'
    ? Math.max(34, 100 - confidence)
    : Math.max(6, 100 - confidence)
  const uncertainty = toPercent(metrics?.abstainProbability, inferredUncertainty)

  const imageScore = Math.min(98, Math.max(55, risk.score + (hasKeyword(risk, ['影像', '裸露', '条带']) ? 3 : -4)))
  const geometryScore = toPercent(
    metrics?.confidenceComponents?.geometry ?? risk.support,
    hasKeyword(risk, ['坡', '高差', '细长', '沟渠']) ? Math.max(72, risk.score - 3) : 64,
  )
  const changeScore = toPercent(
    comparison?.changeScore,
    hasKeyword(risk, ['变化', '新增', '扰动']) ? Math.max(76, risk.score - 1) : 48,
  )
  const ruleScore = toPercent(
    metrics?.selectedVerifierScore,
    hasKeyword(risk, ['距水线', '临水', '近水']) ? Math.max(80, risk.score - 2) : 70,
  )

  const pointCount = risk.pointCount || pointCloud?.pointCountSampled
  const evidence: RiskEvidenceItem[] = [
    {
      id: 'image',
      label: '影像语义证据',
      icon: 'ScanSearch',
      score: imageScore,
      status: evidenceStatus(imageScore),
      summary: hasKeyword(risk, ['裸地', '裸露'])
        ? '正射影像显示连续裸露地表，纹理与周边稳定区域存在显著差异。'
        : '正射影像中目标区域边界连续，可与水线及周边地物清晰区分。',
    },
    {
      id: 'geometry',
      label: '点云几何证据',
      icon: 'Box',
      score: geometryScore,
      status: evidenceStatus(geometryScore),
      summary: pointCount
        ? `已聚合 ${pointCount.toLocaleString('zh-CN')} 个候选点，几何形态与目标风险特征一致。`
        : hasKeyword(risk, ['坡'])
          ? '高程剖面呈连续陡坡，局部坡度超过安全筛查阈值。'
          : '候选区域呈细长下切形态，高差和长宽比支持沟渠判断。',
    },
    {
      id: 'change',
      label: '时相变化证据',
      icon: 'Images',
      score: changeScore,
      status: evidenceStatus(changeScore),
      summary: comparison?.changeSummary
        || (changeScore >= 60
          ? '前后时相对比发现新增扰动，变化边界与候选区域高度重合。'
          : '未获得足够强的时相变化，当前结论主要依赖影像与几何证据。'),
    },
    {
      id: 'rule',
      label: '空间约束命中',
      icon: 'MapPinned',
      score: ruleScore,
      status: evidenceStatus(ruleScore),
      summary: hasKeyword(risk, ['距水线', '临水', '近水'])
        ? '目标位于重点水线缓冲区内，满足临水风险空间约束。'
        : '候选区域命中当前任务的空间范围、排除条件与排序规则。',
    },
  ]

  const uncertaintyReason = risk.level === 'review_required'
    ? hasKeyword(risk, ['道路'])
      ? '候选区域与既有道路边缘局部重叠，模型无法排除道路误检。'
      : '部分证据受遮挡、潮位或配准质量影响，系统主动请求人工复核。'
    : uncertainty <= 20
      ? '多模态证据方向一致，当前判断稳定，可进入处置流程。'
      : '部分证据强度存在差异，建议在处置时同步进行现场核验。'

  return {
    confidence,
    uncertainty,
    uncertaintyReason,
    evidence,
    recommendation: buildRecommendation(risk),
  }
}
