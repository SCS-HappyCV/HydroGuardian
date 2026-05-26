export interface TaskLogData {
  id: string
  taskId: string
  level: 'info' | 'warn' | 'error'
  message: string
  stepName: string
  createdAt: string
}

export type TaskLogFilterKey = keyof Pick<TaskLogData, 'taskId' | 'level' | 'stepName'>
