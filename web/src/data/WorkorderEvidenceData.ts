
export interface WorkorderEvidenceData {
  id: string
  orderId: string
  evidenceType: 'before' | 'after' | 'note'
  title: string
  content: string
  createdAt: string
}

export type WorkorderEvidenceFilterKey = keyof Pick<WorkorderEvidenceData, 'orderId' | 'evidenceType'>
      