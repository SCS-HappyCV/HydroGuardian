import type { TaskResultData, TaskResultFilterKey } from './TaskResultData'

export interface TaskResultVO extends TaskResultData {}

export const taskResultDataList: TaskResultData[] = [
  { id: 'result-1001', taskId: 'task-1001', summary: '融合正射影像、点云与时相变化证据，发现 1 处高风险沟渠和 1 处待复核条带区域。', highRiskCount: 1, mediumRiskCount: 0, lowRiskCount: 0, reviewRequiredCount: 1, createdAt: '2026-05-24T08:18:20Z' },
  { id: 'result-1002', taskId: 'task-1002', summary: '北岸发现 1 处临水陡坡裸地和 1 处阴影遮挡待复核坡面。', highRiskCount: 1, mediumRiskCount: 0, lowRiskCount: 0, reviewRequiredCount: 1, createdAt: '2026-05-25T01:22:30Z' },
  { id: 'result-1003', taskId: 'task-1003', summary: '时相变化检测服务超时，未生成完整风险结果。', highRiskCount: 0, mediumRiskCount: 0, lowRiskCount: 0, reviewRequiredCount: 0, createdAt: '2026-05-24T19:36:15Z' },
  { id: 'result-1004', taskId: 'task-1005', summary: '西港识别到低风险条带扰动，道路相似度较高，建议保持观察。', highRiskCount: 0, mediumRiskCount: 0, lowRiskCount: 1, reviewRequiredCount: 0, createdAt: '2026-05-23T14:29:10Z' },
  { id: 'result-1005', taskId: 'task-1006', summary: '中心河段发现 1 处高风险新增岸线扰动，已形成变化证据。', highRiskCount: 1, mediumRiskCount: 0, lowRiskCount: 0, reviewRequiredCount: 0, createdAt: '2026-05-22T11:10:45Z' },
  { id: 'result-1006', taskId: 'task-1008', summary: '多模态证据验证完成，发现 1 处中风险低矮条带地物。', highRiskCount: 0, mediumRiskCount: 1, lowRiskCount: 0, reviewRequiredCount: 0, createdAt: '2026-05-21T16:15:00Z' },
  { id: 'result-1007', taskId: 'task-1009', summary: '南堤发现连续陡坡裸地区，建议优先开展现场核查。', highRiskCount: 1, mediumRiskCount: 0, lowRiskCount: 0, reviewRequiredCount: 0, createdAt: '2026-05-20T09:05:30Z' },
  { id: 'result-1008', taskId: 'task-1010', summary: '东湾岸线仅出现轻微变化，当前风险总体较低。', highRiskCount: 0, mediumRiskCount: 0, lowRiskCount: 1, reviewRequiredCount: 0, createdAt: '2026-05-19T08:38:25Z' }
]

export function getAll(): TaskResultData[] {
  return taskResultDataList
}

export function getById(id: string): TaskResultData | undefined {
  return taskResultDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<TaskResultFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TaskResultData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = taskResultDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.summary, item.taskId].some((val) => val.toLowerCase().includes(keyword))
    const matchFilter = Object.entries(filter).every(([key, val]) => {
      if (val === undefined) return true
      const itemVal = (item as any)[key]
      return Array.isArray(val) ? val.includes(itemVal) : itemVal === val
    })
    return matchKeyword && matchFilter
  })
  const sortKey = params.sortKey
  if (!sortKey) return result
  return [...result].sort((a, b) => {
    const av = (a as any)[sortKey]
    const bv = (b as any)[sortKey]
    const direction = params.sortDirection === 'desc' ? -1 : 1
    if (av === bv) return 0
    return av > bv ? direction : -direction
  })
}

export function loadPersisted(): TaskResultData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_task_result_data')
  return raw ? (JSON.parse(raw) as TaskResultData[]) : null
}

export function savePersisted(items: TaskResultData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_task_result_data', JSON.stringify(items))
}

export function getByTaskIdVO(taskId: string): TaskResultVO | undefined {
  return taskResultDataList.find((item) => item.taskId === taskId)
}
