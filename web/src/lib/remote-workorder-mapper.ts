import type { RiskEventData } from '@/data/RiskEventData'
import type { WorkorderVO } from '@/data/WorkorderService'
import type { WorkorderReviewVO } from '@/data/WorkorderReviewService'
import type { WorkorderTimelineVO } from '@/data/WorkorderTimelineService'
import type { RemoteWorkorder } from './remote-workorder-types'
import type { SpatialLocationData } from './spatial-location'

function spatialLocation(order: RemoteWorkorder): SpatialLocationData | undefined {
  const value = order.risk_snapshot.location
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined
  const raw = value as Record<string, unknown>
  const longitude = Number(raw.longitude)
  const latitude = Number(raw.latitude)
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return undefined
  const bbox = raw.geographic_bbox
  const geographicBBox = bbox && typeof bbox === 'object' && !Array.isArray(bbox)
    ? {
        west: Number((bbox as Record<string, unknown>).west),
        south: Number((bbox as Record<string, unknown>).south),
        east: Number((bbox as Record<string, unknown>).east),
        north: Number((bbox as Record<string, unknown>).north),
      }
    : undefined
  return {
    longitude,
    latitude,
    projectedX: Number.isFinite(Number(raw.projected_x)) ? Number(raw.projected_x) : undefined,
    projectedY: Number.isFinite(Number(raw.projected_y)) ? Number(raw.projected_y) : undefined,
    epsg: Number.isFinite(Number(raw.epsg)) ? Number(raw.epsg) : undefined,
    crsName: typeof raw.crs_name === 'string' ? raw.crs_name : undefined,
    geographicBBox: geographicBBox && Object.values(geographicBBox).every(Number.isFinite) ? geographicBBox : undefined,
  }
}

export function mapRemoteWorkorder(order: RemoteWorkorder): WorkorderVO {
  return {
    id: order.workorder_id,
    title: order.title,
    riskId: order.region_id || order.candidate_id,
    taskId: order.task_id || undefined,
    assigneeUserId: order.assignee_user_id || undefined,
    reviewerUserId: order.reviewer_user_id || undefined,
    ruleId: order.rule_id || 'agent-risk-rule',
    templateId: 'agent-field-review',
    status: order.status,
    priority: order.priority === 'urgent' ? 'urgent' : 'normal',
    dueAt: order.due_at || order.updated_at,
    createdAt: order.created_at,
    updatedAt: order.updated_at,
    summary: order.summary,
    aiRecommendation: order.recommendation || undefined,
    location: spatialLocation(order),
  }
}

export function mapRemoteRisk(order: RemoteWorkorder): RiskEventData {
  return {
    id: order.region_id || order.candidate_id,
    taskId: order.task_id || order.job_id,
    zoneId: 'agent-analysis-zone',
    ruleId: order.rule_id || 'agent-risk-rule',
    templateId: 'agent-field-review',
    workorderId: order.workorder_id,
    title: order.title,
    description: order.summary,
    level: ['high', 'medium', 'low', 'review_required'].includes(order.risk_level) ? order.risk_level as RiskEventData['level'] : 'review_required',
    score: Math.round(order.score <= 1 ? order.score * 100 : order.score),
    status: order.status === 'closed' ? 'closed' : 'linked',
    evidenceSummary: order.evidence.filter((item) => item.evidence_type === 'source').map((item) => item.title).join('；') || 'Agent 风险证据已随工单归档。',
    evidenceRefs: order.evidence.flatMap((item) => item.artifact_id ? [item.artifact_id] : []),
    riskType: order.risk_type,
    candidateRegionId: order.region_id,
    riskCardId: order.candidate_id,
    candidateScore: order.score,
    triggeredAt: order.created_at,
    updatedAt: order.updated_at,
    location: spatialLocation(order),
  }
}

export function mapRemoteTimeline(order: RemoteWorkorder): WorkorderTimelineVO[] {
  return order.timeline.map((item) => ({
    id: String(item.event_id),
    orderId: order.workorder_id,
    actorUserId: item.actor_user_id || 'agent-system',
    action: item.action as WorkorderTimelineVO['action'],
    note: item.note || '',
    createdAt: item.created_at,
  }))
}

export function mapRemoteReview(order: RemoteWorkorder): WorkorderReviewVO | null {
  const item = order.reviews.at(-1)
  if (!item) return null
  return {
    id: item.review_id,
    orderId: order.workorder_id,
    reviewerUserId: item.reviewer_user_id || 'user-004',
    decision: item.decision,
    comment: item.comment,
    evidenceNote: item.evidence_note || '',
    createdAt: item.created_at,
    reviewerUserName: '人工复核员',
  }
}

export function mapRemoteEvidence(order: RemoteWorkorder) {
  return order.evidence.map((item) => ({
    id: item.evidence_id,
    orderId: order.workorder_id,
    evidenceType: item.evidence_type === 'source' ? 'before' : item.evidence_type,
    title: item.title,
    content: item.content || (item.artifact_id ? `证据资产 ${item.artifact_id}` : ''),
    createdAt: item.created_at,
  }))
}
