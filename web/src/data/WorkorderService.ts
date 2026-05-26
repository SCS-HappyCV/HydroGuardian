import type { WorkorderData, WorkorderFilterKey } from './WorkorderData'
import { getById as getRiskById } from './RiskEventService'
import { getById as getUserById } from './UserService'
import { getById as getRuleById } from './RuleService'
import { getById as getTemplateById } from './TemplateService'

export interface WorkorderVO extends WorkorderData {
  riskTitle?: string
  assigneeUserName?: string
  reviewerUserName?: string
  ruleName?: string
  templateName?: string
}

export const workorderDataList: WorkorderData[] = [
  { id: 'wo-2001', title: '滨海泵站夜间异常处置', riskId: 'risk-1001', assigneeUserId: 'user-002', reviewerUserId: 'user-004', ruleId: 'rule-001', templateId: 'tpl-001', status: 'doing', dueAt: '2026-05-26T08:00:00Z', createdAt: '2026-05-24T08:20:00Z', updatedAt: '2026-05-24T09:10:00Z', summary: '已完成现场核验，等待补充附件。' },
  { id: 'wo-2002', title: '桥涵积水快速处置', riskId: 'risk-1006', assigneeUserId: 'user-003', reviewerUserId: 'user-004', ruleId: 'rule-001', templateId: 'tpl-002', status: 'review', dueAt: '2026-05-25T18:00:00Z', createdAt: '2026-05-22T11:12:00Z', updatedAt: '2026-05-22T15:00:00Z', summary: '处置动作已提交复核。' },
  { id: 'wo-2003', title: '高新区连续高风险治理', riskId: 'risk-1008', assigneeUserId: 'user-001', ruleId: 'rule-001', templateId: 'tpl-003', status: 'todo', dueAt: '2026-05-26T12:00:00Z', createdAt: '2026-05-20T09:06:00Z', updatedAt: '2026-05-20T09:06:00Z', summary: '待分配责任人。' },
  { id: 'wo-2004', title: '北岸排水渠待办整改', riskId: 'risk-1003', assigneeUserId: 'user-002', reviewerUserId: 'user-001', ruleId: 'rule-003', templateId: 'tpl-002', status: 'doing', dueAt: '2026-05-27T09:00:00Z', createdAt: '2026-05-25T01:30:00Z', updatedAt: '2026-05-25T02:10:00Z', summary: '现场已启动清淤。' },
  { id: 'wo-2005', title: '河口片区变化点复核', riskId: 'risk-1010', reviewerUserId: 'user-004', ruleId: 'rule-002', templateId: 'tpl-004', status: 'closed', dueAt: '2026-05-19T20:00:00Z', createdAt: '2026-05-18T13:26:00Z', updatedAt: '2026-05-18T15:00:00Z', summary: '复核通过，工单关闭。' },
  { id: 'wo-2006', title: '西港雨污混接整改', riskId: 'risk-1005', assigneeUserId: 'user-003', reviewerUserId: 'user-002', ruleId: 'rule-004', templateId: 'tpl-004', status: 'closed', dueAt: '2026-05-24T12:00:00Z', createdAt: '2026-05-23T14:30:00Z', updatedAt: '2026-05-23T18:00:00Z', summary: '已整改并完成复核。' }
]

export function getAll(): WorkorderData[] {
  return workorderDataList
}

export function getById(id: string): WorkorderData | undefined {
  return workorderDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<WorkorderFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): WorkorderData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = workorderDataList.filter((item) => {
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
  const raw = localStorage.getItem('hydroguardian_workorder_data')
  return raw ? (JSON.parse(raw) as WorkorderData[]) : null
}

export function savePersisted(items: WorkorderData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_workorder_data', JSON.stringify(items))
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
