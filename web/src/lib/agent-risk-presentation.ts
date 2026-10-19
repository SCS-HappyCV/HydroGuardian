import type { RiskEventData } from '@/data/RiskEventData'
import type {
  AgentArtifactView,
  AgentEvidenceRegionView,
  AgentPresentationSnapshot,
  AgentRiskView,
} from '@/lib/agent-presentation-types'

export interface AgentRiskContext {
  risk: AgentRiskView
  region?: AgentEvidenceRegionView
  artifacts: AgentArtifactView[]
}

export function buildRisksFromAgentSnapshot(
  snapshot: AgentPresentationSnapshot,
  zoneId = 'zone-01',
): RiskEventData[] {
  return snapshot.business.risks.map((risk) => {
    const region = snapshot.evidence.regions.find((item) => item.regionId === risk.regionId)
    return {
      id: risk.riskId,
      taskId: snapshot.task.taskId,
      zoneId,
      ruleId: risk.ruleId || 'agent-risk-candidate-v1',
      templateId: 'tpl-001',
      title: risk.title,
      description: risk.summary,
      level: risk.riskLevel,
      score: risk.score ?? region?.score ?? 0,
      status: risk.reviewRequired ? 'review_required' : 'new',
      evidenceSummary: region?.summary || snapshot.evidence.summary,
      triggeredAt: snapshot.createdAt,
      updatedAt: snapshot.createdAt,
      candidateRegionId: region?.regionId,
      riskType: risk.riskType,
      bboxPixel: region?.bboxPixel,
      polygonPixel: region?.polygonPixel,
      location: region?.geographicCenter ? {
        longitude: region.geographicCenter.longitude,
        latitude: region.geographicCenter.latitude,
        projectedX: region.projectedCenter?.x,
        projectedY: region.projectedCenter?.y,
        epsg: snapshot.spatial?.primary?.epsg,
        crsName: snapshot.spatial?.primary?.crsName,
        geographicBBox: region.geographicBBox,
      } : undefined,
      evidenceRefs: [...risk.evidenceRefs],
      reviewRequired: risk.reviewRequired,
      sourceTool: risk.sourceTool,
      scoreKind: risk.scoreKind,
      qualityGate: risk.qualityGate,
    }
  })
}

export function getAgentRiskContext(
  snapshot: AgentPresentationSnapshot,
  riskId: string,
): AgentRiskContext | undefined {
  const risk = snapshot.business.risks.find((item) => item.riskId === riskId)
  if (!risk) return undefined
  const region = snapshot.evidence.regions.find((item) => item.regionId === risk.regionId)
  const artifactIds = new Set([...risk.evidenceRefs, ...(region?.artifactRefs || [])])
  return {
    risk,
    region,
    artifacts: snapshot.evidence.artifacts.filter((item) => artifactIds.has(item.artifactId)),
  }
}
