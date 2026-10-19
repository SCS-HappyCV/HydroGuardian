import type { WorkorderData, WorkorderFilterKey } from './WorkorderData'
import { getById as getRiskById } from './RiskEventService'
import { getById as getUserById } from './UserService'
import { getById as getRuleById } from './RuleService'
import { getById as getTemplateById } from './TemplateService'

const STORAGE_KEY = 'hydroguardian_workorder_data_competition_v1'

export interface WorkorderVO extends WorkorderData {
  riskTitle?: string
  assigneeUserName?: string
  reviewerUserName?: string
  ruleName?: string
  templateName?: string
}

export const workorderDataList: WorkorderData[] = [
  { id: 'wo-2001', title: '近水疑似沟渠现场核查', riskId: 'risk-1001', taskId: 'task-1001', caseId: 'case-near-water-disturbance-001', assigneeUserId: 'user-002', reviewerUserId: 'user-004', ruleId: 'rule-001', templateId: 'tpl-a01', status: 'closed', priority: 'urgent', dueAt: '2026-05-24T18:00:00Z', createdAt: '2026-05-24T08:20:00Z', updatedAt: '2026-05-24T11:18:00Z', summary: '现场确认存在新近开挖沟渠，已完成警戒、回填处置和复核关闭。', aiRecommendation: '立即核查沟渠施工主体与影响范围，设置临水警戒，完成处置前后影像留档。' },
  { id: 'wo-2002', title: '新增岸线扰动快速处置', riskId: 'risk-1006', assigneeUserId: 'user-003', reviewerUserId: 'user-004', ruleId: 'rule-001', templateId: 'tpl-a01', status: 'review', dueAt: '2026-05-25T18:00:00Z', createdAt: '2026-05-22T11:12:00Z', updatedAt: '2026-05-22T15:00:00Z', summary: '现场处置及前后对比材料已提交复核。' },
  { id: 'wo-2003', title: '南堤陡坡裸地现场核验', riskId: 'risk-1008', assigneeUserId: 'user-001', ruleId: 'rule-001', templateId: 'tpl-a01', status: 'todo', dueAt: '2026-05-26T12:00:00Z', createdAt: '2026-05-20T09:06:00Z', updatedAt: '2026-05-20T09:06:00Z', summary: '待分配现场核验责任人。' },
  { id: 'wo-2004', title: '北岸临水陡坡防护核查', riskId: 'risk-1003', assigneeUserId: 'user-002', reviewerUserId: 'user-001', ruleId: 'rule-003', templateId: 'tpl-a01', status: 'doing', dueAt: '2026-05-27T09:00:00Z', createdAt: '2026-05-25T01:30:00Z', updatedAt: '2026-05-25T02:10:00Z', summary: '现场坡面核查正在进行。' },
  { id: 'wo-2005', title: '河口片区变化点复核', riskId: 'risk-1010', reviewerUserId: 'user-004', ruleId: 'rule-002', templateId: 'tpl-a02', status: 'closed', dueAt: '2026-05-19T20:00:00Z', createdAt: '2026-05-18T13:26:00Z', updatedAt: '2026-05-18T15:00:00Z', summary: '复核通过，工单关闭。' },
  { id: 'wo-2006', title: '西港条带扰动复核', riskId: 'risk-1005', assigneeUserId: 'user-003', reviewerUserId: 'user-002', ruleId: 'rule-004', templateId: 'tpl-a02', status: 'closed', dueAt: '2026-05-24T12:00:00Z', createdAt: '2026-05-23T14:30:00Z', updatedAt: '2026-05-23T18:00:00Z', summary: '现场确认属于既有道路边缘，已完成复核关闭。' }
]

export function getAll(): WorkorderData[] {
  return loadPersisted() || workorderDataList
}

export function getById(id: string): WorkorderData | undefined {
  return getAll().find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<WorkorderFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): WorkorderData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = getAll().filter((item) => {
    const matchKeyword = !keyword || [item.id, item.title, item.summary, item.status].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): WorkorderData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem(STORAGE_KEY)
  return raw ? (JSON.parse(raw) as WorkorderData[]) : null
}

export function savePersisted(items: WorkorderData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
}

export function update(id: string, patch: Partial<WorkorderData>): WorkorderData | undefined {
  const items = getAll()
  const index = items.findIndex((item) => item.id === id)
  if (index < 0) return undefined

  const next = {
    ...items[index],
    ...patch,
    id,
    updatedAt: patch.updatedAt || new Date().toISOString(),
  }
  items[index] = next
  savePersisted(items)
  return next
}

export function getByIdVO(id: string): WorkorderVO | undefined {
  const item = getById(id)
  if (!item) return undefined
  const risk = getRiskById(item.riskId)
  return {
    ...item,
    riskTitle: risk?.title,
    assigneeUserName: item.assigneeUserId ? getUserById(item.assigneeUserId)?.name : undefined,
    reviewerUserName: item.reviewerUserId ? getUserById(item.reviewerUserId)?.name : undefined,
    ruleName: getRuleById(item.ruleId)?.name,
    templateName: getTemplateById(item.templateId)?.name
  }
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<WorkorderFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): WorkorderVO[] {
  return query(params).map((item) => getByIdVO(item.id)).filter((item): item is WorkorderVO => Boolean(item))
}
