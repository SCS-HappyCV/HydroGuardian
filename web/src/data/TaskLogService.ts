import type { TaskLogData, TaskLogFilterKey } from './TaskLogData'

export interface TaskLogVO extends TaskLogData {}

export const taskLogDataList: TaskLogData[] = [
  { id: 'log-1001', taskId: 'task-1001', level: 'info', message: '任务理解完成：目标为近水细长沟渠，排除对象为道路。', stepName: '任务理解', createdAt: '2026-05-24T08:11:10Z' },
  { id: 'log-1002', taskId: 'task-1001', level: 'info', message: '正射影像、点云和前后时相场景样本已准备完成。', stepName: '场景准备', createdAt: '2026-05-24T08:11:35Z' },
  { id: 'log-1003', taskId: 'task-1001', level: 'info', message: '生成 2 个候选区域：1 个高风险，1 个因道路重叠转人工复核。', stepName: '风险研判', createdAt: '2026-05-24T08:15:20Z' },
  { id: 'log-1004', taskId: 'task-1002', level: 'info', message: '任务排队成功，等待执行资源释放。', stepName: '排队', createdAt: '2026-05-25T01:11:40Z' },
  { id: 'log-1005', taskId: 'task-1002', level: 'warn', message: '图层加载较慢，已切换为轻量模式。', stepName: '图层加载', createdAt: '2026-05-25T01:17:20Z' },
  { id: 'log-1006', taskId: 'task-1002', level: 'info', message: '巡查步骤已完成 68%，等待最终风险汇总。', stepName: '执行中', createdAt: '2026-05-25T01:22:10Z' },
  { id: 'log-1007', taskId: 'task-1003', level: 'info', message: '任务启动成功，开始对齐前后时相影像。', stepName: '变化检测', createdAt: '2026-05-24T19:31:10Z' },
  { id: 'log-1008', taskId: 'task-1003', level: 'error', message: '变化检测服务返回超时，当前步骤重试失败。', stepName: '变化检测', createdAt: '2026-05-24T19:35:42Z' },
  { id: 'log-1009', taskId: 'task-1004', level: 'info', message: '任务已加入队列，优先级为低。', stepName: '排队', createdAt: '2026-05-25T06:45:20Z' },
  { id: 'log-1010', taskId: 'task-1005', level: 'info', message: '巡检完成，条带区域道路相似度较高，风险等级为低。', stepName: '结果汇总', createdAt: '2026-05-23T14:29:10Z' },
  { id: 'log-1011', taskId: 'task-1006', level: 'info', message: '前后时相发现新增岸线扰动，已生成变化掩膜。', stepName: '变化检测', createdAt: '2026-05-22T11:08:30Z' },
  { id: 'log-1012', taskId: 'task-1012', level: 'info', message: '复盘报告生成完成，可导出历史对比摘要。', stepName: '报告生成', createdAt: '2026-05-18T13:25:40Z' }
]

export function getAll(): TaskLogData[] {
  return taskLogDataList
}

export function getById(id: string): TaskLogData | undefined {
  return taskLogDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<TaskLogFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TaskLogData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = taskLogDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.message, item.stepName, item.level].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): TaskLogData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_task_log_data')
  return raw ? (JSON.parse(raw) as TaskLogData[]) : null
}

export function savePersisted(items: TaskLogData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_task_log_data', JSON.stringify(items))
}

export function queryByTaskId(taskId: string): TaskLogVO[] {
  return taskLogDataList.filter((item) => item.taskId === taskId)
}
