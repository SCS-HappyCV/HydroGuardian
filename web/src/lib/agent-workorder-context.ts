import type { RiskEventData } from '@/data/RiskEventData'
import type { WorkorderData } from '@/data/WorkorderData'
import type { WorkorderEvidenceData } from '@/data/WorkorderEvidenceData'
import { localAgentRuntime } from '@/lib/local-agent-runtime'
import { getRemoteAgentBinding, getRemoteAgentSnapshot } from '@/lib/remote-agent-storage'
import { buildRisksFromAgentSnapshot, getAgentRiskContext } from '@/lib/agent-risk-presentation'
import type { AgentPresentationSnapshot } from '@/lib/agent-presentation-types'

export interface AgentWorkorderContext {
  snapshot: AgentPresentationSnapshot
  risk: RiskEventData
  evidence: WorkorderEvidenceData[]
}

export function getAgentWorkorderContext(workorder: WorkorderData): AgentWorkorderContext | undefined {
  if (!workorder.taskId) return undefined
  const snapshot = getRemoteAgentBinding(workorder.taskId)
    ? getRemoteAgentSnapshot(workorder.taskId)
    : localAgentRuntime.restore(workorder.taskId)
  if (!snapshot) return undefined
  const risk = buildRisksFromAgentSnapshot(snapshot).find((item) => item.id === workorder.riskId)
  if (!risk) return undefined
  const context = getAgentRiskContext(snapshot, risk.id)
  const evidence = (context?.artifacts || []).map((artifact): WorkorderEvidenceData => ({
    id: `${workorder.id}-${artifact.artifactId}`,
    orderId: workorder.id,
    evidenceType: artifact.mediaType.includes('image') ? 'before' : 'note',
    title: artifact.title,
    content: context?.region?.summary || snapshot.evidence.summary,
    createdAt: snapshot.createdAt,
  }))
  return { snapshot, risk, evidence }
}
