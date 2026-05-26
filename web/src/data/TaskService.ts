import type { TaskData, TaskFilterKey } from './TaskData'
import { getById as getTemplateById } from './TaskTemplateService'
import { getById as getZoneById } from './ZoneService'
import { getById as getUserById } from './UserService'
import { getById as getTaskResultById } from './TaskResultService'

export interface TaskVO extends TaskData {
  templateName?: string
  zoneName?: string
  createdByUserName?: string
  resultSummary?: string
}

export const taskDataList: TaskData[] = [
  {
    id: 'task-1001',
    name: '滨海泵站夜巡分析',
    inputText: '请检查滨海泵站周边夜间异常水位波动并生成风险清单',
    templateId: 'tpl-001',
    zoneId: 'zone-01',
    sampleId: 'sample-001',
    priority: 'high',
    status: 'success',
    progress: 100,
    createdAt: '2026-05-24T08:10:00Z',
    startedAt: '2026-05-24T08:11:00Z',
    finishedAt: '2026-05-24T08:18:30Z',
    createdByUserId: 'user-001',
    updatedAt: '2026-05-24T08:18:30Z'
  },
  {
    id: 'task-1002',
    name: '北岸排水渠例行巡查',
    inputText: '巡查北岸排水渠淤积与泵站连通情况，优先关注低洼区',
    templateId: 'tpl-002',
    zoneId: 'zone-02',
    sampleId: 'sample-003',
    priority: 'medium',
    status: 'running',
    progress: 68,
    createdAt: '2026-05-25T01:10:00Z',
    startedAt: '2026-05-25T01:11:30Z',
    createdByUserId: 'user-002',
    updatedAt: '2026-05-25T01:22:10Z'
  },
  {
    id: 'task-1003',
    name: '南堤闸门应急复核',
    inputText: '对南堤闸门的应急状态做一次快速复核，检查是否存在回流风险',
    templateId: 'tpl-003',
    zoneId: 'zone-03',
    sampleId: 'sample-005',
    priority: 'high',
    status: 'failed',
    progress: 100,
    createdAt: '2026-05-24T19:30:00Z',
    startedAt: '2026-05-24T19:31:00Z',
    finishedAt: '2026-05-24T19:36:15Z',
    createdByUserId: 'user-003',
    updatedAt: '2026-05-24T19:36:15Z'
  },
  {
    id: 'task-1004',
    name: '东湾片区雨后巡检',
    inputText: '根据最近降雨情况检查东湾片区内涝积水点和排水能力',
    templateId: 'tpl-004',
    zoneId: 'zone-04',
    sampleId: 'sample-006',
    priority: 'low',
    status: 'queued',
    progress: 0,
    createdAt: '2026-05-25T06:45:00Z',
    createdByUserId: 'user-001',
    updatedAt: '2026-05-25T06:45:00Z'
  },
  {
    id: 'task-1005',
    name: '西港工业区复巡',
    inputText: '复巡西港工业区雨污混接点，输出整改建议与风险分级',
    templateId: 'tpl-001',
    zoneId: 'zone-05',
    sampleId: 'sample-002',
    priority: 'medium',
    status: 'success',
    progress: 100,
    createdAt: '2026-05-23T14:20:00Z',
    startedAt: '2026-05-23T14:20:30Z',
    finishedAt: '2026-05-23T14:29:10Z',
    createdByUserId: 'user-004',
    updatedAt: '2026-05-23T14:29:10Z'
  },
  {
    id: 'task-1006',
    name: '中心城区桥涵积水监测',
    inputText: '监测中心城区桥涵下穿点的积水变化趋势并形成告警摘要',
    templateId: 'tpl-002',
    zoneId: 'zone-01',
    sampleId: 'sample-004',
    priority: 'high',
    status: 'success',
    progress: 100,
    createdAt: '2026-05-22T11:00:00Z',
    startedAt: '2026-05-22T11:02:00Z',
    finishedAt: '2026-05-22T11:10:45Z',
    createdByUserId: 'user-002',
    updatedAt: '2026-05-22T11:10:45Z'
  },
  {
    id: 'task-1007',
    name: '沿河绿廊巡查',
    inputText: '查看沿河绿廊边坡稳定性和排水沟通畅程度',
    templateId: 'tpl-004',
    zoneId: 'zone-06',
    sampleId: 'sample-001',
    priority: 'low',
    status: 'running',
    progress: 42,
    createdAt: '2026-05-25T07:20:00Z',
    startedAt: '2026-05-25T07:20:20Z',
    createdByUserId: 'user-003',
    updatedAt: '2026-05-25T07:33:40Z'
  },
  {
    id: 'task-1008',
    name: '泵站群联动演练',
    inputText: '执行泵站群联动演练并记录控制节点风险',
    templateId: 'tpl-003',
    zoneId: 'zone-02',
    sampleId: 'sample-007',
    priority: 'medium',
    status: 'success',
    progress: 100,
    createdAt: '2026-05-21T16:05:00Z',
    startedAt: '2026-05-21T16:06:10Z',
    finishedAt: '2026-05-21T16:15:00Z',
    createdByUserId: 'user-001',
    updatedAt: '2026-05-21T16:15:00Z'
  },
  {
    id: 'task-1009',
    name: '高新区重点点位快检',
    inputText: '对高新区重点点位进行快速检查，关注高风险与待复核问题',
    templateId: 'tpl-001',
    zoneId: 'zone-03',
    sampleId: 'sample-008',
    priority: 'high',
    status: 'failed',
    progress: 100,
    createdAt: '2026-05-20T09:00:00Z',
    startedAt: '2026-05-20T09:01:00Z',
    finishedAt: '2026-05-20T09:05:30Z',
    createdByUserId: 'user-004',
    updatedAt: '2026-05-20T09:05:30Z'
  },
  {
    id: 'task-1010',
    name: '滨海新区排涝能力评估',
    inputText: '评估滨海新区当前排涝能力并对比上次结果',
    templateId: 'tpl-002',
    zoneId: 'zone-04',
    sampleId: 'sample-003',
    priority: 'medium',
    status: 'success',
    progress: 100,
    createdAt: '2026-05-19T08:30:00Z',
    startedAt: '2026-05-19T08:31:00Z',
    finishedAt: '2026-05-19T08:38:25Z',
    createdByUserId: 'user-002',
    updatedAt: '2026-05-19T08:38:25Z'
  },
  {
    id: 'task-1011',
    name: '老城区排水盲区排查',
    inputText: '排查老城区排水盲区和疑似回流点，输出优先处置建议',
    templateId: 'tpl-004',
    zoneId: 'zone-05',
    sampleId: 'sample-005',
    priority: 'high',
    status: 'queued',
    progress: 0,
    createdAt: '2026-05-25T07:55:00Z',
    createdByUserId: 'user-003',
    updatedAt: '2026-05-25T07:55:00Z'
  },
  {
    id: 'task-1012',
    name: '河口片区防汛复盘',
    inputText: '复盘河口片区近三次巡检结果，梳理新增与消失的风险点',
    templateId: 'tpl-003',
    zoneId: 'zone-06',
    sampleId: 'sample-006',
    priority: 'low',
    status: 'success',
    progress: 100,
    createdAt: '2026-05-18T13:15:00Z',
    startedAt: '2026-05-18T13:16:20Z',
    finishedAt: '2026-05-18T13:25:40Z',
    createdByUserId: 'user-001',
    updatedAt: '2026-05-18T13:25:40Z'
  }
]

export function getAll(): TaskData[] {
  return taskDataList
}

export function getById(id: string): TaskData | undefined {
  return taskDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<TaskFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TaskData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = taskDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.name, item.inputText, item.status, item.priority].some((val) => val.toLowerCase().includes(keyword))
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
    if (av === bv) return 0
    const direction = params.sortDirection === 'desc' ? -1 : 1
    return av > bv ? direction : -direction
  })
}

export function loadPersisted(): TaskData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_task_data')
  return raw ? (JSON.parse(raw) as TaskData[]) : null
}

export function savePersisted(items: TaskData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_task_data', JSON.stringify(items))
}

export function getByIdVO(id: string): TaskVO | undefined {
  const item = getById(id)
  if (!item) return undefined
  return {
    ...item,
    templateName: getTemplateById(item.templateId)?.name,
    zoneName: getZoneById(item.zoneId)?.name,
    createdByUserName: getUserById(item.createdByUserId)?.name,
    resultSummary: getTaskResultById(item.id)?.summary
  }
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<TaskFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TaskVO[] {
  return query(params).map((item) => getByIdVO(item.id)).filter((item): item is TaskVO => Boolean(item))
}
