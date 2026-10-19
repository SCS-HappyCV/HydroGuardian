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
  { id: 'risk-1001', taskId: 'task-1001', zoneId: 'zone-01', ruleId: 'rule-001', templateId: 'tpl-001', workorderId: 'wo-2001', title: '近水细长沟渠疑似开挖', description: '候选区域紧邻水线，呈连续细长形态，且前后时相出现新增裸露扰动。', level: 'high', score: 92, status: 'linked', evidenceSummary: '距水线 18m；长宽比 6.4；点云高差 1.8m；变化置信度 0.91', triggeredAt: '2026-05-24T08:16:00Z', updatedAt: '2026-05-24T08:20:00Z' },
  { id: 'risk-1002', taskId: 'task-1001', zoneId: 'zone-01', ruleId: 'rule-002', templateId: 'tpl-001', title: '近水条带区域待复核', description: '区域形态符合沟渠特征，但与既有道路边缘局部重叠，模型主动转人工复核。', level: 'review_required', score: 67, status: 'review_required', evidenceSummary: '距水线 27m；道路重叠率 0.34；综合置信度 0.62；模型不确定性较高', triggeredAt: '2026-05-24T08:16:45Z', updatedAt: '2026-05-24T08:21:00Z' },
  { id: 'risk-1003', taskId: 'task-1002', zoneId: 'zone-02', ruleId: 'rule-003', templateId: 'tpl-002', title: '北岸临水陡坡裸地', description: '点云显示岸坡坡度较高，影像中植被覆盖不足，具备冲刷风险。', level: 'high', score: 88, status: 'new', evidenceSummary: '平均坡度 38°；高于水线 6.2m；裸地占比 73%', triggeredAt: '2026-05-25T01:20:10Z', updatedAt: '2026-05-25T01:22:00Z' },
  { id: 'risk-1004', taskId: 'task-1002', zoneId: 'zone-02', ruleId: 'rule-002', templateId: 'tpl-002', title: '阴影遮挡坡面待复核', description: '局部坡面被树冠阴影遮挡，影像证据不足，需结合现场照片复核。', level: 'review_required', score: 61, status: 'review_required', evidenceSummary: '点云坡度 31°；影像有效覆盖 48%；综合置信度 0.58', triggeredAt: '2026-05-25T01:21:10Z', updatedAt: '2026-05-25T01:22:10Z' },
  { id: 'risk-1005', taskId: 'task-1005', zoneId: 'zone-05', ruleId: 'rule-004', templateId: 'tpl-004', title: '西港岸线轻微条带扰动', description: '存在细长裸露区域，但与道路相似度较高，当前判定为低风险。', level: 'low', score: 41, status: 'closed', evidenceSummary: '距水线 42m；道路相似度 0.71；未发现显著高程变化', triggeredAt: '2026-05-23T14:25:30Z', updatedAt: '2026-05-23T14:29:10Z' },
  { id: 'risk-1006', taskId: 'task-1006', zoneId: 'zone-01', ruleId: 'rule-001', templateId: 'tpl-003', workorderId: 'wo-2002', title: '中心河段新增岸线扰动', description: '前后时相对比发现岸线附近新增裸地区域，变化范围连续扩大。', level: 'high', score: 90, status: 'linked', evidenceSummary: '新增变化面积 286㎡；距水线 12m；变化置信度 0.93', triggeredAt: '2026-05-22T11:08:00Z', updatedAt: '2026-05-22T11:12:00Z' },
  { id: 'risk-1007', taskId: 'task-1008', zoneId: 'zone-02', ruleId: 'rule-003', templateId: 'tpl-003', title: '北岸低矮条带地物', description: '几何特征符合沟渠候选，但未观察到明显时相变化。', level: 'medium', score: 58, status: 'closed', evidenceSummary: '长宽比 4.8；平均高差 0.9m；变化置信度 0.32', triggeredAt: '2026-05-21T16:11:00Z', updatedAt: '2026-05-21T16:15:00Z' },
  { id: 'risk-1008', taskId: 'task-1009', zoneId: 'zone-03', ruleId: 'rule-001', templateId: 'tpl-002', workorderId: 'wo-2003', title: '南堤连续陡坡裸地区', description: '多个相邻候选区同时命中临水、陡坡和裸地条件。', level: 'high', score: 95, status: 'linked', evidenceSummary: '连续 3 处候选；最大坡度 46°；裸地占比 81%', triggeredAt: '2026-05-20T09:03:00Z', updatedAt: '2026-05-20T09:06:00Z' },
  { id: 'risk-1009', taskId: 'task-1010', zoneId: 'zone-04', ruleId: 'rule-004', templateId: 'tpl-003', title: '东湾岸线轻微变化', description: '局部纹理发生变化，但变化面积小且远离重点水线。', level: 'low', score: 35, status: 'closed', evidenceSummary: '变化面积 38㎡；距水线 76m；变化置信度 0.44', triggeredAt: '2026-05-19T08:36:00Z', updatedAt: '2026-05-19T08:38:25Z' },
  { id: 'risk-1010', taskId: 'task-1012', zoneId: 'zone-06', ruleId: 'rule-002', templateId: 'tpl-003', title: '河口新增变化区域待复核', description: '历史对比中发现新增区域，但潮位差异可能造成水陆边界偏移。', level: 'review_required', score: 63, status: 'review_required', evidenceSummary: '变化面积 114㎡；水线偏移 6m；综合置信度 0.60', triggeredAt: '2026-05-18T13:22:00Z', updatedAt: '2026-05-18T13:25:40Z' }
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
