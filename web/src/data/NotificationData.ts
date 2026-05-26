export interface NotificationData {
  id: string
  title: string
  content: string
  type: 'info' | 'warning' | 'error'
  isRead: boolean
  createdAt: string
}

export type NotificationFilterKey = keyof Pick<NotificationData, 'type' | 'isRead'>
