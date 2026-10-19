import { describe, expect, it } from 'vitest'
import { mapRemoteWorkorder } from './remoteWorkorderMapper'
import type { RemoteWorkorder } from './remoteWorkorderTypes'

function remoteOrder(overrides: Partial<RemoteWorkorder> = {}): RemoteWorkorder {
  return {
    workorder_id: 'wo_remote_1',
    job_id: 'job_remote_1',
    candidate_id: 'risk_1',
    region_id: 'region_1',
    task_id: 'task_1',
    status: 'todo',
    title: '临水扰动核查',
    summary: '检测到新增变化区域',
    risk_type: 'near_water_change',
    risk_level: 'high',
    score: 0.91,
    recommendation: '现场核验并回传影像',
    assignee_user_id: 'user-xuran',
    reviewer_user_id: 'reviewer-1',
    due_at: '2026-08-15T10:00:00Z',
    risk_snapshot: {
      area: '北岸重点水域',
      location: { longitude: 109.65, latitude: 23.59 },
    },
    created_at: '2026-08-14T08:00:00Z',
    updated_at: '2026-08-14T09:00:00Z',
    version: 2,
    evidence: [{
      evidence_id: 'evidence-1',
      evidence_type: 'source',
      artifact_id: 'artifact-1',
      title: '变化检测结果',
      content: '新增扰动区域',
      media_type: 'image/png',
      metadata: { role: 'change_mask', score: 0.93 },
      created_at: '2026-08-14T08:00:00Z',
    }],
    reviews: [],
    timeline: [],
    ...overrides,
  }
}

describe('remoteWorkorderMapper', () => {
  it('maps assigned todo orders and real evidence previews', () => {
    const item = mapRemoteWorkorder(remoteOrder())
    expect(item.status).toBe('assigned')
    expect(item.confidence).toBe(91)
    expect(item.longitude).toBe(109.65)
    expect(item.evidence[0].type).toBe('change')
    expect(item.evidence[0].previewUrl).toContain('/v1/assets/artifact-1/preview')
  })

  it('does not request image previews for structured artifacts', () => {
    const item = mapRemoteWorkorder(remoteOrder({
      evidence: [{
        ...remoteOrder().evidence[0],
        media_type: 'application/json',
        metadata: {
          artifact_media_type: 'application/json',
          artifact_metadata: { spatial_role: 'quality_report' },
        },
      }],
    }))
    expect(item.evidence[0].title).toBe('模型质量报告')
    expect(item.evidence[0].previewKind).toBe('report')
    expect(item.evidence[0].previewUrl).toBeUndefined()
  })

  it('maps server closure states', () => {
    expect(mapRemoteWorkorder(remoteOrder({ status: 'doing' })).status).toBe('in_progress')
    expect(mapRemoteWorkorder(remoteOrder({ status: 'review' })).status).toBe('reviewed')
    expect(mapRemoteWorkorder(remoteOrder({ status: 'closed' })).status).toBe('closed')
  })
})
