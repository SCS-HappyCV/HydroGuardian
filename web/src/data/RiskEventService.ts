import type { RiskEventData, RiskEventFilterKey } from './RiskEventData'
import { getById as getZoneById } from './ZoneService'
import { getById as getRuleById } from './RuleService'
import { getById as getTemplateById } from './TemplateService'
import { getById as getWorkorderById } from './WorkorderService'
import { getById as getTaskById } from './TaskService'

export interface RiskEventVO extends RiskEventData {
  zoneName?: string
  ruleName?: string
  templateName?: string
  workorderTitle?: string
  taskName?: string
}

export const riskEventDataList: RiskEventData[] = [
  { id: 'risk-1001', taskId: 'task-1001', zoneId: 'zone-01', ruleId: 'rule-001', templateId: 'tpl-001', workorderId: 'wo-2001', title: '滨海泵站夜间水位异常', description: '夜间水位连续上升并触发泵站联动规则。', level: 'high', score: 92, status: 'linked', evidenceSummary: '水位曲线抬升、摄像头异常闪烁', triggeredAt: '2026-05-24T08:16:00Z', updatedAt: '2026-05-24T08:20:00Z' },
  { id: 'risk-1002', taskId: 'task-1001', zoneId: 'zone-01', ruleId: 'rule-002', templateId: 'tpl-001', title: '滨海泵站边坡渗漏', description: '边坡渗漏与排水效率下降同时出现。', level: 'medium', score: 71, status: 'review_required', evidenceSummary: '边坡湿痕、排水流速降低', triggeredAt: '2026-05-24T08:16:45Z', updatedAt: '2026-05-24T08:21:00Z' },
  { id: 'risk-1003', taskId: 'task-1002', zoneId: 'zone-02', ruleId: 'rule-003', templateId: 'tpl-002', title: '北岸排水渠淤积告警', description: '连续两次巡查均发现淤积片区扩大。', level: 'high', score: 88, status: 'new', evidenceSummary: '淤积面积扩大、流速下降', triggeredAt: '2026-05-25T01:20:10Z', updatedAt: '2026-05-25T01:22:00Z' },
  { id: 'risk-1004', taskId: 'task-1002', zoneId: 'zone-02', ruleId: 'rule-002', templateId: 'tpl-002', title: '北岸低洼区待复核点', description: '低洼区积水疑似反射干扰，需人工复核。', level: 'review_required', score: 64, status: 'review_required', evidenceSummary: '积水反光、边界模糊', triggeredAt: '2026-05-25T01:21:10Z', updatedAt: '2026-05-25T01:22:10Z' },
  { id: 'risk-1005', taskId: 'task-1005', zoneId: 'zone-05', ruleId: 'rule-004', templateId: 'tpl-004', title: '西港雨污混接轻微异常', description: '异常程度较低但已超过模板阈值。', level: 'low', score: 41, status: 'closed', evidenceSummary: '管线混接点轻微回流', triggeredAt: '2026-05-23T14:25:30Z', updatedAt: '2026-05-23T14:29:10Z' },
  { id: 'risk-1006', taskId: 'task-1006', zoneId: 'zone-01', ruleId: 'rule-001', templateId: 'tpl-002', workorderId: 'wo-2002', title: '桥涵下穿点积水聚集', description: '桥涵结构下方积水增长过快。', level: 'high', score: 90, status: 'linked', evidenceSummary: '积水深度超阈值、车流阻断', triggeredAt: '2026-05-22T11:08:00Z', updatedAt: '2026-05-22T11:12:00Z' },
  { id: 'risk-1007', taskId: 'task-1008', zoneId: 'zone-04', ruleId: 'rule-003', templateId: 'tpl-003', title: '泵站联动响应迟缓', description: '联动响应比历史均值略慢。', level: 'medium', score: 58, status: 'closed', evidenceSummary: '联动延迟 12 秒', triggeredAt: '2026-05-21T16:11:00Z', updatedAt: '2026-05-21T16:15:00Z' },
  { id: 'risk-1008', taskId: 'task-1009', zoneId: 'zone-03', ruleId: 'rule-001', templateId: 'tpl-003', workorderId: 'wo-2003', title: '高新区连续高风险点', description: '多个点位连续触发高等级风险。', level: 'high', score: 95, status: 'linked', evidenceSummary: '连续 3 处高风险，建议立即处置', triggeredAt: '2026-05-20T09:03:00Z', updatedAt: '2026-05-20T09:06:00Z' },
  { id: 'risk-1009', taskId: 'task-1010', zoneId: 'zone-06', ruleId: 'rule-004', templateId: 'tpl-004', title: '滨海新区轻微排涝波动', description: '整体稳定但局部指标略有变化。', level: 'low', score: 35, status: 'closed', evidenceSummary: '排涝曲线轻微波动', triggeredAt: '2026-05-19T08:36:00Z', updatedAt: '2026-05-19T08:38:25Z' },
  { id: 'risk-1010', taskId: 'task-1012', zoneId: 'zone-06', ruleId: 'rule-002', templateId: 'tpl-004', title: '河口片区待复核变化点', description: '历史对比中新增的疑似变化点。', level: 'review_required', score: 63, status: 'review_required', evidenceSummary: '新增变化点，需复核', triggeredAt: '2026-05-18T13:22:00Z', updatedAt: '2026-05-18T13:25:40Z' }
]

export function getAll(): RiskEventData[] {
  return riskEventDataList
}

export function getById(id: string): RiskEventData | undefined {
  return riskEventDataList.find((item) => item.id === id)
}

export function query(params: {
  keyword?: string
  filter?: Partial<Record<RiskEventFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): RiskEventData[] {
  const keyword = params.keyword?.trim().toLowerCase()
  const filter = params.filter ?? {}
  const result = riskEventDataList.filter((item) => {
    const matchKeyword = !keyword || [item.id, item.title, item.description, item.level, item.status].some((val) => val.toLowerCase().includes(keyword))
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

export function loadPersisted(): RiskEventData[] | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem('hydroguardian_risk_event_data')
  return raw ? (JSON.parse(raw) as RiskEventData[]) : null
}

export function savePersisted(items: RiskEventData[]): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem('hydroguardian_risk_event_data', JSON.stringify(items))
}

export function getByIdVO(id: string): RiskEventVO | undefined {
  const item = getById(id)
  if (!item) return undefined
  return {
    ...item,
    zoneName: getZoneById(item.zoneId)?.name,
    ruleName: getRuleById(item.ruleId)?.name,
    templateName: getTemplateById(item.templateId)?.name,
    workorderTitle: item.workorderId ? getWorkorderById(item.workorderId)?.title : undefined,
    taskName: getTaskById(item.taskId)?.name
  }
}

export function queryVO(params: {
  keyword?: string
  filter?: Partial<Record<RiskEventFilterKey, string | string[]>>
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}): RiskEventVO[] {
  return query(params).map((item) => getByIdVO(item.id)).filter((item): item is RiskEventVO => Boolean(item))
}
