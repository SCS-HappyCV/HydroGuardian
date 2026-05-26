
export interface AttachmentData {
  id: string
  orderId: string
  fileName: string
  fileType: 'image' | 'pdf' | 'doc'
  url: string
  uploadedByUserId: string
  uploadedAt: string
}

export type AttachmentFilterKey = keyof Pick<AttachmentData, 'orderId' | 'fileType' | 'uploadedByUserId'>
      