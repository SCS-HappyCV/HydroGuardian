export interface WorkorderTimelineData {
  id: string
  orderId: string
  actorUserId: string
  action: 'created' | 'assigned' | 'processing' | 'review_requested' | 'reviewed' | 'closed'
  note: string
  createdAt: string
}

export type WorkorderTimelineFilterKey = keyof Pick<WorkorderTimelineData, 'orderId' | 'actorUserId' | 'action'>
