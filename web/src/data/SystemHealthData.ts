export interface SystemHealthData {
  id: string
  serviceKey: string
  serviceName: string
  category: 'backend' | 'model' | 'database'
  status: 'healthy' | 'degraded' | 'down'
  latencyMs: number
  errorCount: number
  lastCheckedAt: string
}

export type SystemHealthFilterKey = keyof Pick<SystemHealthData, 'serviceKey' | 'category' | 'status'>
