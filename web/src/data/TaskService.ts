// 任务数据服务：统一管理任务静态样本、本地持久化和视图对象转换。
import type { TaskData, TaskFilterKey } from './TaskData'
import { getById as getTemplateById } from './TaskTemplateService'
import { getById as getZoneById } from './ZoneService'
import { getById as getUserById } from './UserService'
import { getByTaskIdVO as getTaskResultByTaskId } from './TaskResultService'

const STORAGE_KEY = 'hydroguardian_task_data_competition_v1'

export interface TaskVO extends TaskData {
  templateName?: string
  zoneName?: string
  createdByUserName?: string
  resultSummary?: string
}

export const taskDataList: TaskData[] = [
  {
    id: 'task-1001',
    name: '近水扰动与疑似沟渠筛查',
    inputText: '筛查近水扰动区域，重点识别细长沟渠并排除道路，按风险高低排序',
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
    name: '北岸陡坡裸地排查',
    inputText: '找出北岸高于水线的陡坡裸地区域，并按坡度和临水距离排序',
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
    name: '南堤近水扰动复核',
    inputText: '对比南堤前后时相影像，检查是否出现新增近水扰动区域',
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
    name: '东湾岸线综合巡查',
    inputText: '综合筛查东湾岸线附近沟渠、裸地与新增扰动，输出证据和建议',
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
    name: '西港近水沟渠复巡',
    inputText: '复巡西港岸线附近疑似沟渠，排除道路后输出风险分级',
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
    name: '中心河段岸线变化检测',
    inputText: '对比中心河段前后影像，定位岸线附近新增变化并形成证据摘要',
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
    name: '沿河绿廊边坡巡查',
    inputText: '筛查沿河绿廊高陡裸地与近水异常区域，按风险高低排序',
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
    name: '北岸多模态证据演练',
    inputText: '融合北岸正射影像与点云，验证候选区域的高程和几何证据',
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
    name: '南堤裸地风险快检',
    inputText: '快速筛查南堤临水陡坡裸地，关注高风险与低置信待复核区域',
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
    name: '东湾岸线变化评估',
    inputText: '评估东湾岸线本期新增扰动并与上次巡查结果对比',
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
    name: '西港疑似沟渠排查',
    inputText: '排查西港近水细长区域，排除道路干扰并输出优先处置建议',
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
    name: '河口片区时相复盘',
    inputText: '复盘河口片区近三次遥感巡查结果，梳理新增与消失的扰动区域',
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

// 同步内存任务列表，保证页面跳转后同一运行时读取到最新任务。
function syncTaskDataList(items: TaskData[]): TaskData[] {
  taskDataList.splice(0, taskDataList.length, ...items)
  return taskDataList
}

// 读取全部任务；浏览器环境优先使用 localStorage，SSR 阶段使用静态样本。
export function getAll(): TaskData[] {
  const persisted = loadPersisted()
  return persisted ? syncTaskDataList(persisted) : taskDataList
}

// 按任务 ID 查询单个任务，包含用户在任务工作坊中新建的本地任务。
export function getById(id: string): TaskData | undefined {
  return getAll().find((item) => item.id === id)
}

// 按关键词、筛选和排序条件查询任务列表。
export function query(params: {
  keyword?: string
  filter?: Partial<Record<TaskFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TaskData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = getAll().filter((item) => {
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

// 从 localStorage 读取任务列表，解析失败时回退为空值以避免页面崩溃。
export function loadPersisted(): TaskData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return null

  try {
    const items = JSON.parse(raw) as TaskData[]
    return Array.isArray(items) ? items : null
  } catch {
    return null
  }
}

// 保存任务列表到 localStorage，并同步当前运行时内存列表。
export function savePersisted(items: TaskData[]): void {
  syncTaskDataList(items)
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
}

// 查询任务视图对象，附带模板、区域、创建人和结果摘要。
export function getByIdVO(id: string): TaskVO | undefined {
  const item = getById(id)
  if (!item) return undefined
  return {
    ...item,
    templateName: getTemplateById(item.templateId)?.name,
    zoneName: getZoneById(item.zoneId)?.name,
    createdByUserName: getUserById(item.createdByUserId)?.name,
    resultSummary: getTaskResultByTaskId(item.id)?.summary
  }
}

// 查询任务视图对象列表，供表格和历史页面直接渲染。
export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<TaskFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): TaskVO[] {
  return query(params).map((item) => getByIdVO(item.id)).filter((item): item is TaskVO => Boolean(item))
}
