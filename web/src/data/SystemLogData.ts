export interface SystemLogData {
  id: string
  serviceHealthId: string
  taskId?: string
  level: 'info' | 'warn' | 'error'
  message: string
  createdAt: string
}

export type SystemLogFilterKey = keyof Pick<SystemLogData, 'serviceHealthId' | 'taskId' | 'level'>
