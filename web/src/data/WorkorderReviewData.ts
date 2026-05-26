export interface WorkorderReviewData {
  id: string
  orderId: string
  reviewerUserId: string
  decision: 'approved' | 'rejected'
  comment: string
  evidenceNote: string
  createdAt: string
}

export type WorkorderReviewFilterKey = keyof Pick<WorkorderReviewData, 'orderId' | 'reviewerUserId' | 'decision'>
