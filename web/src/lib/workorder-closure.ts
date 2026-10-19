import type { WorkorderData } from '@/data/WorkorderData'
import type { WorkorderTimelineVO } from '@/data/WorkorderTimelineService'
import type { WorkorderEvidenceData } from '@/data/WorkorderEvidenceData'
import type { WorkorderReviewVO } from '@/data/WorkorderReviewService'

export interface ClosureStage {
  id: 'discovered' | 'confirmed' | 'dispatched' | 'feedback' | 'closed'
  label: string
  shortLabel: string
  icon: string
  status: 'completed' | 'current' | 'pending'
  time?: string
  actor?: string
  note: string
  evidence?: string
}

function eventByAction(timeline: WorkorderTimelineVO[], actions: string[]): WorkorderTimelineVO | undefined {
  return timeline.find((item) => actions.includes(item.action))
}

export function buildClosureStages(
  workorder: WorkorderData,
  timeline: WorkorderTimelineVO[],
  evidence: WorkorderEvidenceData[] = [],
  review?: WorkorderReviewVO | null,
): ClosureStage[] {
  const created = eventByAction(timeline, ['created'])
  const confirmed = eventByAction(timeline, ['assigned'])
  const dispatched = eventByAction(timeline, ['processing'])
  const feedback = eventByAction(timeline, ['review_requested'])
  const closed = eventByAction(timeline, ['reviewed', 'closed'])
  const rank = { todo: 1, doing: 3, review: 4, closed: 5 }[workorder.status]

  const statusAt = (index: number): ClosureStage['status'] => {
    if (rank > index) return 'completed'
    if (rank === index) return workorder.status === 'closed' ? 'completed' : 'current'
    return 'pending'
  }

  return [
    {
      id: 'discovered',
      label: 'AI 发现风险',
      shortLabel: 'AI 发现',
      icon: 'ScanSearch',
      status: 'completed',
      time: created?.createdAt || workorder.createdAt,
      actor: 'HydroGuardian 智能体',
      note: created?.note || '多模态智能体识别风险并形成证据包。',
      evidence: '风险区域、置信度与处置建议',
    },
    {
      id: 'confirmed',
      label: '人工确认',
      shortLabel: '人工确认',
      icon: 'UserRoundCheck',
      status: statusAt(2),
      time: confirmed?.createdAt,
      actor: confirmed?.actorUserName,
      note: confirmed?.note || '等待人工核对风险判断和关键证据。',
      evidence: confirmed ? '确认意见与责任范围' : undefined,
    },
    {
      id: 'dispatched',
      label: '派发处置',
      shortLabel: '派发处置',
      icon: 'Send',
      status: statusAt(3),
      time: dispatched?.createdAt,
      actor: dispatched?.actorUserName,
      note: dispatched?.note || '等待派发现场处置任务。',
      evidence: dispatched ? `责任人：${dispatched.actorUserName || '现场巡检人员'}` : undefined,
    },
    {
      id: 'feedback',
      label: '现场反馈',
      shortLabel: '现场反馈',
      icon: 'Camera',
      status: statusAt(4),
      time: feedback?.createdAt,
      actor: feedback?.actorUserName,
      note: feedback?.note || '等待现场回传定位照片和处理说明。',
      evidence: evidence.find((item) => item.evidenceType === 'after')?.title,
    },
    {
      id: 'closed',
      label: '复核关闭',
      shortLabel: '复核关闭',
      icon: 'BadgeCheck',
      status: statusAt(5),
      time: closed?.createdAt || review?.createdAt,
      actor: closed?.actorUserName || review?.reviewerUserName,
      note: closed?.note || review?.comment || '等待复核处置效果并关闭工单。',
      evidence: review?.evidenceNote,
    },
  ]
}
