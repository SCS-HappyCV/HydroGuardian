import { parseAgentEventData, translateAgentMessage } from '@/api/execution-display'
import type { TaskData } from '@/data/TaskData'
import type { TaskExecutionSnapshot } from '@/lib/api-contracts'

export type AgentStageStatus = 'pending' | 'running' | 'completed' | 'error'

export interface AgentStageView {
  id: string
  index: string
  title: string
  agent: string
  icon: string
  status: AgentStageStatus
  result: string
  duration: string
  tools: string[]
}

interface StageDefinition {
  id: string
  title: string
  agent: string
  icon: string
  threshold: number
  tracePrefixes: string[]
  result: string
  tools: string[]
}

const STAGE_DEFINITIONS: StageDefinition[] = [
  { id: 'understand', title: '理解巡查任务', agent: '任务理解智能体', icon: 'MessageSquareText', threshold: 8, tracePrefixes: ['parse_task'], result: '识别目标、空间关系与排除条件', tools: ['LLM / 规则解析'] },
  { id: 'program', title: '编译空间程序', agent: '任务理解智能体', icon: 'Braces', threshold: 20, tracePrefixes: ['build_program'], result: '生成可执行 field-schema program', tools: ['Program Builder'] },
  { id: 'scene', title: '准备多模态场景', agent: '证据执行智能体', icon: 'DatabaseZap', threshold: 34, tracePrefixes: ['prepare_scene_sample'], result: '对齐正射影像、点云和时相资产', tools: ['Scene Preprocess'] },
  { id: 'evidence', title: '检索三维证据', agent: '证据执行智能体', icon: 'Cuboid', threshold: 58, tracePrefixes: ['execute_3d', 'compile_evidence'], result: '生成候选区域与几何证据', tools: ['hydro-program3d'] },
  { id: 'change', title: '检测时相变化', agent: '证据执行智能体', icon: 'Images', threshold: 76, tracePrefixes: ['detect_change', 'maybe_detect_change'], result: '对比前后影像并生成变化掩膜', tools: ['Change Detection'] },
  { id: 'risk', title: '评估与排序风险', agent: '风险研判智能体', icon: 'ShieldAlert', threshold: 86, tracePrefixes: ['assess_risk'], result: '融合证据，判断风险和不确定性', tools: ['Risk Engine'] },
  { id: 'recommend', title: '生成处置建议', agent: '建议生成智能体', icon: 'Lightbulb', threshold: 93, tracePrefixes: ['generate_recommendation'], result: '形成现场核查与补采建议', tools: ['Recommendation Engine'] },
  { id: 'workorder', title: '创建闭环工单', agent: '闭环管理智能体', icon: 'ClipboardCheck', threshold: 98, tracePrefixes: ['create_work_order', 'persist_case'], result: '关联风险、证据与责任流程', tools: ['Case / Work Order'] },
]

function stageMatches(stage: string, prefixes: string[]): boolean {
  const normalized = stage.toLowerCase()
  return prefixes.some((prefix) => normalized === prefix || normalized.startsWith(`${prefix}.`))
}

function resolveDuration(snapshot: TaskExecutionSnapshot | null, prefixes: string[]): string {
  if (!snapshot) return '—'
  const event = snapshot.trace.find((item) => stageMatches(item.stage, prefixes))
  if (!event) return '—'
  const data = parseAgentEventData(event)
  const duration = data?.duration_ms
  return typeof duration === 'number' || typeof duration === 'string' ? `${duration}ms` : '<1s'
}

function resolveResult(snapshot: TaskExecutionSnapshot | null, definition: StageDefinition): string {
  if (!snapshot) return definition.result
  const event = [...snapshot.trace].reverse().find((item) => stageMatches(item.stage, definition.tracePrefixes))
  if (!event) return definition.result
  return translateAgentMessage(event.message)
}

export function buildAgentStages(
  progress: number,
  taskStatus: TaskData['status'],
  snapshot: TaskExecutionSnapshot | null,
): AgentStageView[] {
  const finished = taskStatus === 'success'
  const failed = taskStatus === 'failed'

  return STAGE_DEFINITIONS.map((definition, index) => {
    const hasTrace = snapshot?.trace.some((item) => stageMatches(item.stage, definition.tracePrefixes)) ?? false
    const hasError = snapshot?.errors.some((item) => stageMatches(item.stage, definition.tracePrefixes)) ?? false
    let status: AgentStageStatus = 'pending'

    if (hasError) status = 'error'
    else if (finished || hasTrace || progress > definition.threshold + 10) status = 'completed'
    else if (failed && progress >= definition.threshold) status = 'error'
    else if (taskStatus === 'running' && progress >= definition.threshold) status = 'running'

    return {
      id: definition.id,
      index: String(index + 1).padStart(2, '0'),
      title: definition.title,
      agent: definition.agent,
      icon: definition.icon,
      status,
      result: resolveResult(snapshot, definition),
      duration: resolveDuration(snapshot, definition.tracePrefixes),
      tools: definition.tools,
    }
  })
}

export interface EvidenceFeedItem {
  id: string
  title: string
  description: string
  icon: string
  color: string
  ready: boolean
  metric: string
}

export function buildEvidenceFeed(progress: number, snapshot: TaskExecutionSnapshot | null): EvidenceFeedItem[] {
  return [
    { id: 'image', title: '正射影像证据', description: '水线与候选区域纹理已提取', icon: 'Image', color: 'primary', ready: progress >= 34, metric: '分辨率 0.2m' },
    { id: 'pointcloud', title: '点云几何证据', description: '高程、坡度与长宽比已计算', icon: 'Cuboid', color: 'violet', ready: progress >= 58, metric: '高差 1.8m' },
    { id: 'change', title: '时相变化证据', description: '前后影像对齐与变化掩膜', icon: 'Images', color: 'accent', ready: progress >= 76, metric: '置信度 0.91' },
    { id: 'risk', title: '综合风险证据', description: snapshot?.reviewRequired ? '证据存在冲突，已转人工复核' : '多模态证据已完成融合验证', icon: 'ShieldCheck', color: 'warning', ready: progress >= 86, metric: snapshot ? `${snapshot.riskScore} 分` : '92 分' },
  ]
}

