// 执行结果展示适配器：把后端 trace、error、状态和诊断字段转换为前端中文展示模型。
import type { TaskLogData } from '@/data/TaskLogData'
import type { AgentErrorItem, AgentTraceItem, TaskExecutionSnapshot } from '@/lib/api-contracts'

export type AgentEventLevel = 'info' | 'warn' | 'error'

export interface AgentTimelineEvent {
  id: string
  stage: string
  stageLabel: string
  level: AgentEventLevel
  levelLabel: string
  message: string
  detail: string
  createdAt: string
}

const STAGE_LABELS: Record<string, string> = {
  parse_task: '任务解析',
  'parse_task.llm_fallback': '任务解析降级',
  build_program: '巡检程序构建',
  prepare_scene_sample: '场景样本准备',
  'prepare_scene_sample.manifest': '场景清单加载',
  'prepare_scene_sample.manifest_service': '场景清单查询',
  'prepare_scene_sample.asset': '场景资产解析',
  'prepare_scene_sample.load': '场景样本加载',
  'prepare_scene_sample.validate': '场景样本校验',
  'execute_3d.discovery': '3D 服务发现',
  'execute_3d.health': '3D 服务健康检查',
  'execute_3d.execute': '3D Program 执行',
  'execute_3d.compile_evidence': '3D 证据编译请求',
  execute_3d: '3D 执行',
  compile_evidence: '证据包编译',
  detect_change: '变化检测',
  maybe_detect_change: '变化检测',
  assess_risk: '风险研判',
  generate_recommendation: '建议生成',
  create_work_order: '工单草稿生成',
  persist_case: '案例持久化',
  'persist_case.snapshot': '案例快照持久化',
  'persist_case.work_order': '工单持久化',
}

const MESSAGE_LABELS: Record<string, string> = {
  'task intent parsed': '任务意图解析完成',
  'LLM task parser failed; rule fallback used': 'LLM 任务解析失败，已切换到规则解析',
  'program bundle built': '巡检程序构建完成',
  'task needs clarification': '任务需要补充说明',
  'task is outside the current executable scope': '任务超出当前可执行范围',
  'failed to load scene asset manifest': '场景资产清单加载失败',
  'failed to query scene asset manifest': '场景资产清单查询失败',
  'failed to resolve scene file asset': '场景文件资产解析失败',
  'failed to load scene tensor sample': '场景张量样本加载失败',
  'missing scene tensor sample': '缺少场景张量样本',
  'invalid scene tensor sample': '场景张量样本无效',
  'scene sample prepared': '场景样本准备完成',
  'scene tensor sample or selected program is missing': '场景张量样本或已选程序缺失',
  'hydro-program3d base url resolved': '3D 服务地址解析完成',
  'hydro-program3d health checked': '3D 服务健康检查完成',
  'hydro-program3d health check skipped': '3D 服务健康检查已跳过',
  'hydro-program3d request succeeded': '3D 服务请求成功',
  'hydro-program3d request failed': '3D 服务请求失败',
  'hydro-program3d execution failed': '3D 执行失败，已进入降级证据流程',
  'response JSON root must be an object': '响应 JSON 根节点必须是对象',
  '/compile_evidence returned non-object evidence_pack': '证据编译接口返回的 evidence_pack 不是对象',
  'evidence_pack.candidate_regions must be a list': '证据包 candidate_regions 必须是列表',
  'evidence_pack.evidence_summary must be a list': '证据包 evidence_summary 必须是列表',
  'evidence pack compiled': '证据包编译完成',
  'risk card generated': '风险卡生成完成',
  'recommendation card generated': '处置建议生成完成',
  'work order draft generated': '工单草稿生成完成',
  'temporal task has no pre/post image references': '时序任务缺少灾前/灾后影像引用，已跳过变化检测',
  'change detector generated a temporal change mask': '变化检测生成了时序变化掩膜',
  'evidence pack compiled without textual summary': '证据包已编译，但缺少文本摘要',
}

const STATUS_LABELS: Record<string, string> = {
  SUCCESS: '执行成功',
  SUCCEEDED: '执行成功',
  COMPLETED: '执行完成',
  DONE: '执行完成',
  FAILED: '执行失败',
  ERROR: '执行异常',
  ABSTAINED: '系统拒答',
  REVIEW_REQUIRED: '需要人工复核',
  INTENT_PARSED: '任务已解析',
  PROGRAM_READY: '程序已就绪',
  SCENE_SAMPLE_READY: '场景样本已就绪',
  RAW_EXECUTOR_READY: '3D 原始结果已返回',
  EVIDENCE_READY: '证据包已就绪',
  RISK_READY: '风险卡已就绪',
  RECOMMENDATION_READY: '建议已就绪',
  WORK_ORDER_READY: '工单草稿已就绪',
}

const RISK_LEVEL_LABELS: Record<string, string> = {
  HIGH: '高风险',
  MEDIUM: '中风险',
  LOW: '低风险',
  REVIEW_REQUIRED: '待复核',
  UNKNOWN: '未知风险',
}

const EVIDENCE_STATUS_LABELS: Record<string, string> = {
  success: '证据可用',
  failed: '证据失败',
  unavailable: '证据不可用',
  REVIEW_REQUIRED: '证据待复核',
  FAILED: '证据失败',
  SUCCESS: '证据可用',
}

const PERSISTENCE_STATUS_LABELS: Record<string, string> = {
  success: '持久化成功',
  partial: '部分持久化',
  failed: '持久化失败',
  SUCCESS: '持久化成功',
  PARTIAL: '部分持久化',
  FAILED: '持久化失败',
}

const ERROR_TYPE_LABELS: Record<string, string> = {
  timeout: '请求超时',
  connect_error: '连接失败',
  http_status: 'HTTP 状态异常',
  invalid_json: '响应 JSON 无效',
  unknown: '未知错误',
  precondition_failed: '前置条件不满足',
  missing_execute_input: '执行输入缺失',
  service_discovery_failed: '服务发现失败',
  unexpected_error: '非预期错误',
}

const STAGE_PROGRESS: Record<string, number> = {
  parse_task: 10,
  'parse_task.llm_fallback': 10,
  build_program: 22,
  prepare_scene_sample: 35,
  'prepare_scene_sample.manifest': 35,
  'prepare_scene_sample.manifest_service': 35,
  'prepare_scene_sample.asset': 35,
  'prepare_scene_sample.load': 35,
  'prepare_scene_sample.validate': 35,
  'execute_3d.discovery': 45,
  'execute_3d.health': 55,
  'execute_3d.execute': 68,
  'execute_3d.compile_evidence': 78,
  execute_3d: 68,
  compile_evidence: 82,
  detect_change: 86,
  maybe_detect_change: 86,
  assess_risk: 90,
  generate_recommendation: 94,
  create_work_order: 97,
  persist_case: 100,
  'persist_case.snapshot': 100,
  'persist_case.work_order': 100,
}

// 判断字符串是否已包含中文，避免把后端已经中文化的文案重复加工。
function hasChineseText(value: string): boolean {
  return /[\u4e00-\u9fff]/.test(value)
}

// 统一标准化后端枚举键，兼容大小写、空格和短横线。
function normalizeKey(value: string): string {
  return value.trim().replace(/-/g, '_').toUpperCase()
}

// 安全解析 trace/error 中的 dataJson 字段。
export function parseAgentEventData(item: AgentTraceItem | AgentErrorItem): Record<string, unknown> | null {
  if (!item.dataJson) return null

  try {
    const data = JSON.parse(item.dataJson) as unknown
    return data && typeof data === 'object' && !Array.isArray(data) ? data as Record<string, unknown> : null
  } catch {
    return { raw: item.dataJson }
  }
}

// 获取 trace 阶段的中文名称；未知阶段保留原始键但加上业务前缀。
export function getStageLabel(stage: string): string {
  const normalized = stage.trim()
  if (!normalized) return '未标记阶段'
  return STAGE_LABELS[normalized] ?? STAGE_LABELS[normalized.toLowerCase()] ?? `未映射阶段：${normalized}`
}

// 获取日志等级中文名称。
export function getLogLevelLabel(level: AgentEventLevel | string): string {
  if (level === 'error') return '错误'
  if (level === 'warn') return '警告'
  return '信息'
}

// 获取执行状态中文名称。
export function getExecutionStatusLabel(status: string): string {
  const key = normalizeKey(status)
  return STATUS_LABELS[key] ?? (status || '未知状态')
}

// 获取证据状态中文名称。
export function getEvidenceStatusLabel(status: string): string {
  const raw = status.trim()
  const key = normalizeKey(raw)
  return EVIDENCE_STATUS_LABELS[raw] ?? EVIDENCE_STATUS_LABELS[key] ?? (raw || '未知证据状态')
}

// 获取风险等级中文名称。
export function getRiskLevelLabel(riskLevel: string): string {
  const key = normalizeKey(riskLevel)
  return RISK_LEVEL_LABELS[key] ?? (riskLevel || '未知风险')
}

// 获取 case 持久化状态中文名称。
export function getPersistenceStatusLabel(status: string): string {
  const raw = status.trim()
  const key = normalizeKey(raw)
  return PERSISTENCE_STATUS_LABELS[raw] ?? PERSISTENCE_STATUS_LABELS[key] ?? (raw || '未知持久化状态')
}

// 获取错误类型中文名称。
function getErrorTypeLabel(errorType: unknown): string {
  if (typeof errorType !== 'string' || !errorType.trim()) return ''
  const key = normalizeKey(errorType)
  return ERROR_TYPE_LABELS[errorType] ?? ERROR_TYPE_LABELS[key] ?? errorType
}

// 将常见英文 trace message 转为中文；未知且已经是中文的文案直接保留。
export function translateAgentMessage(message: string): string {
  const text = message.trim()
  if (!text) return '阶段执行完成'
  if (MESSAGE_LABELS[text]) return MESSAGE_LABELS[text]
  if (hasChineseText(text)) return text

  const missingFieldsMatch = text.match(/^(.+?) missing required fields: (.+)$/)
  if (missingFieldsMatch) {
    return `${missingFieldsMatch[1]} 缺少必填字段：${missingFieldsMatch[2]}`
  }

  const listMatch = text.match(/^(.+?) must be a list$/)
  if (listMatch) {
    return `${listMatch[1]} 必须是列表`
  }

  if (/timeout/i.test(text)) return `请求超时：${text}`
  if (/connection|connect/i.test(text)) return `连接失败：${text}`
  if (/not found|404/i.test(text)) return `资源未找到：${text}`
  if (/unauthorized|401/i.test(text)) return `鉴权失败：${text}`
  if (/forbidden|403/i.test(text)) return `权限不足：${text}`
  if (/failed/i.test(text)) return `执行失败：${text}`
  if (/success|succeeded/i.test(text)) return `执行成功：${text}`

  return `原始信息：${text}`
}

// 将 dataJson 中常见诊断字段整理成中文摘要。
export function formatEventDataSummary(data: Record<string, unknown> | null): string {
  if (!data) return ''

  const parts: string[] = []
  const append = (label: string, value: unknown) => {
    if (value === undefined || value === null || value === '') return
    if (typeof value === 'boolean') {
      parts.push(`${label}：${value ? '是' : '否'}`)
      return
    }
    if (Array.isArray(value)) {
      parts.push(`${label}：${value.join('、')}`)
      return
    }
    parts.push(`${label}：${String(value)}`)
  }

  append('目标类型', data.target)
  append('解析来源', data.parser_source)
  append('服务地址', data.base_url)
  append('服务名', data.service_name)
  append('HTTP 状态', data.status_code)
  append('耗时', typeof data.duration_ms === 'number' ? `${data.duration_ms}ms` : data.duration_ms)
  append('第几次尝试', data.attempt)
  append('是否重试', data.will_retry)
  append('风险等级', typeof data.risk_level === 'string' ? getRiskLevelLabel(data.risk_level) : data.risk_level)
  append('置信度', data.confidence)
  append('错误类型', getErrorTypeLabel(data.error_type))
  append('错误阶段', typeof data.stage === 'string' ? getStageLabel(data.stage) : data.stage)
  append('错误原因', data.reason)
  append('校验问题', data.issues)
  append('原始内容', data.raw)

  return parts.slice(0, 8).join('；')
}

// 将单条 trace/error 转换为统一时间线事件。
function toTimelineEvent(
  item: AgentTraceItem | AgentErrorItem,
  level: AgentEventLevel,
  index: number,
  localTaskId: string,
  createdAt: string,
): AgentTimelineEvent {
  const data = parseAgentEventData(item)
  return {
    id: `api-${level}-${localTaskId}-${index}`,
    stage: item.stage,
    stageLabel: getStageLabel(item.stage),
    level,
    levelLabel: getLogLevelLabel(level),
    message: translateAgentMessage(item.message),
    detail: formatEventDataSummary(data),
    createdAt,
  }
}

// 构造真实执行快照的完整时间线，trace 在前、error 追加在后。
export function buildAgentTimeline(snapshot: TaskExecutionSnapshot): AgentTimelineEvent[] {
  const traceEvents = snapshot.trace.map((item, index) => toTimelineEvent(item, 'info', index, snapshot.localTaskId, snapshot.createdAt))
  const errorEvents = snapshot.errors.map((item, index) => toTimelineEvent(item, 'error', index, snapshot.localTaskId, snapshot.createdAt))
  return [...traceEvents, ...errorEvents]
}

// 将真实执行快照转换为监控页日志流模型。
export function buildTaskLogsFromSnapshot(snapshot: TaskExecutionSnapshot): TaskLogData[] {
  return buildAgentTimeline(snapshot).map((event) => ({
    id: event.id,
    taskId: snapshot.localTaskId,
    level: event.level,
    message: event.detail ? `${event.message}\n${event.detail}` : event.message,
    stepName: event.stageLabel,
    createdAt: event.createdAt,
  }))
}

// 根据 trace 阶段计算回放进度；同步执行已返回终态时显示 100%。
export function getSnapshotProgress(snapshot: TaskExecutionSnapshot): number {
  const status = normalizeKey(snapshot.executionStatus)
  if (['SUCCESS', 'SUCCEEDED', 'COMPLETED', 'DONE', 'FAILED', 'ERROR', 'ABSTAINED', 'REVIEW_REQUIRED'].includes(status)) {
    return 100
  }

  const progress = snapshot.trace.reduce((maxProgress, item) => {
    return Math.max(maxProgress, STAGE_PROGRESS[item.stage] ?? STAGE_PROGRESS[item.stage.toLowerCase()] ?? 0)
  }, 0)

  return progress || 5
}
