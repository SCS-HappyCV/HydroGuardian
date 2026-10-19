import { AGENT_CAPABILITIES } from '@/lib/agent-capability-catalog'
import type { AgentExecutionStatus, AgentPresentationSnapshot, AgentTraceView, AgentWorkflowStepStatus } from '@/lib/agent-presentation-types'
import type { RemoteAgentAdaptedResult } from '@/lib/remote-agent-result-adapter'
import type { RemoteAgentEvent, RemoteAgentJob, RemoteAgentStep, RemoteAgentWorker } from '@/lib/remote-agent-types'
import type { RemoteAgentTaskBinding } from '@/lib/remote-agent-storage'

const toolNames: Record<string, string> = {
  point_semantic_segmentation: '点云语义分析', image_change_detection: '前后时相变化检测', language_guided_point_segmentation: '语言引导点云定位', geometry_relation_analysis: '空间几何关系分析', result_quality_verification: '结果质量验证',
}

function executionStatus(status: RemoteAgentJob['status']): AgentExecutionStatus {
  if (status === 'queued_planning') return 'idle'
  if (status === 'planning' || status === 'queued_execution') return 'preparing'
  if (status === 'executing') return 'running'
  if (status === 'succeeded') return 'completed'
  if (status === 'blocked_expert') return 'blocked'
  if (status === 'cancelled') return 'cancelled'
  return 'failed'
}
function stepStatus(status: RemoteAgentStep['status']): AgentWorkflowStepStatus {
  if (status === 'succeeded') return 'completed'
  if (status === 'running' || status === 'dispatched') return 'running'
  if (status === 'failed' || status === 'lost') return 'failed'
  if (status === 'cancelled') return 'skipped'
  return 'pending'
}

function record(value: unknown): Record<string, any> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, any> : undefined
}

interface PlannedStep {
  stepId: string
  tool: string
  dependsOn: string[]
  verificationPolicy?: 'auto' | 'required' | 'skip'
}

function verificationPolicy(value: unknown): PlannedStep['verificationPolicy'] {
  return value === 'required' || value === 'skip' || value === 'auto' ? value : undefined
}

function plannedSteps(job: RemoteAgentJob): PlannedStep[] {
  const action = record(job.plan?.action)
  if (!action) return []
  if (action.type === 'tool_call' && typeof action.tool === 'string') return [{ stepId: 'expert-1', tool: action.tool, dependsOn: [], verificationPolicy: verificationPolicy(action.verification) }]
  if (action.type !== 'workflow' || !Array.isArray(action.steps)) return []
  return action.steps.flatMap((item: unknown) => {
    const step = record(item)
    return step && typeof step.step_id === 'string' && typeof step.tool === 'string'
      ? [{ stepId: step.step_id, tool: step.tool, dependsOn: Array.isArray(step.depends_on) ? step.depends_on.map(String) : [], verificationPolicy: verificationPolicy(step.verification) }]
      : []
  })
}

const phaseNames: Record<string, string> = {
  started: '专家已接单，正在准备运行环境', loading: '正在加载模型与场景数据', inference: '模型正在分析场景', postprocessing: '正在整理分析结果', uploading: '正在归档证据产物', completed: '专家执行已完成',
}

const eventMessages: Record<string, string> = {
  created: '任务已进入智能分析队列',
  claimed: '规划服务已接收任务',
  planning_succeeded: '已完成任务理解并生成专家协作路径',
  planning_failed: '任务规划未能完成',
  step_dispatched: '专家任务已完成调度',
  step_progress: '专家正在执行分析',
  step_succeeded: '专家分析完成，结果已回传',
  step_failed: '专家执行出现异常',
  step_lost: '专家节点连接中断',
  execution_retry: '任务正在重新调度执行',
  execution_succeeded: '全部专家步骤执行完成',
  execution_batch_succeeded: '当前执行批次完成，正在接续新增专家步骤',
  workflow_patch_queued: 'Agent 已按人工指令追加专家步骤',
  workflow_patch_succeeded: '人工追加的专家步骤已完成',
  workflow_patch_failed: '新增专家步骤执行未完成，原有结果继续保留',
  execution_failed: '智能分析任务执行失败',
  execution_blocked: '所需专家能力暂时不可用',
  cancelled: '任务已停止',
  retried: '任务已重新加入执行队列',
}

function eventCategory(eventType: string, tool?: string, hasArtifacts = false): AgentTraceView['category'] {
  if (eventType.includes('plan') || eventType === 'claimed') return 'planning'
  if (tool === 'result_quality_verification' || eventType.includes('quality') || eventType.includes('verif')) return 'quality'
  if (eventType.includes('artifact') || hasArtifacts) return 'artifact'
  if (eventType.startsWith('step_')) return 'expert'
  return 'system'
}

export function mapRemoteAgentEvent(event: RemoteAgentEvent): AgentTraceView {
  const payload = record(event.payload) || {}
  const tool = typeof payload.tool === 'string' ? payload.tool : undefined
  const workerId = typeof payload.worker_id === 'string' ? payload.worker_id : undefined
  const phase = typeof payload.phase === 'string' ? payload.phase : undefined
  const rawProgress = typeof payload.progress === 'number' ? payload.progress : undefined
  const progress = rawProgress === undefined ? undefined : Math.round(rawProgress <= 1 ? rawProgress * 100 : rawProgress)
  const attempt = typeof payload.attempt === 'number' ? payload.attempt : undefined
  const error = record(payload.error)
  const result = record(payload.result)
  const artifacts = record(result?.artifacts)
  const hasArtifacts = Boolean(artifacts && Object.keys(artifacts).length)
  const statusTransition = event.to_status ? `${event.from_status || '任务'} → ${event.to_status}` : ''
  const phaseMessage = phase ? phaseNames[phase] : undefined
  const detail = error && typeof error.code === 'string' ? `错误码 ${error.code}` : undefined
  const baseMessage = eventMessages[event.event_type] || statusTransition || event.event_type.replaceAll('_', ' ')
  const message = [baseMessage, phaseMessage, progress === undefined ? undefined : `${progress}%`, detail].filter(Boolean).join(' · ')
  return {
    traceId: String(event.event_id),
    stage: event.event_type,
    level: event.event_type.includes('failed') || event.event_type.includes('lost') ? 'error' : event.event_type.includes('retry') || event.event_type.includes('blocked') ? 'warning' : 'info',
    message,
    timestamp: event.created_at,
    category: eventCategory(event.event_type, tool, hasArtifacts),
    tool,
    toolLabel: tool ? toolNames[tool] || tool.replaceAll('_', ' ') : undefined,
    workerId,
    phase: phase ? phaseNames[phase] || phase : undefined,
    progress,
    attempt,
  }
}

function runtimeSummary(step: RemoteAgentStep): string {
  if (step.error) return String(step.error.message || step.error.code || '专家执行出现异常')
  if (step.status === 'succeeded') return step.tool === 'result_quality_verification' ? '质量门禁已完成，结果可信度与完整性已核验' : '专家分析已完成，结果产物已归档'
  if (step.status === 'dispatched') return `已调度至 ${step.worker_id || '可用专家节点'}`
  if (step.status === 'running') return phaseNames[step.phase] || `由 ${step.worker_id || '专家节点'} 执行中`
  if (step.status === 'cancelled') return '该步骤已取消'
  return '等待前置步骤完成后调度'
}

function runtimeArtifacts(step?: RemoteAgentStep): string[] {
  return Object.values((step?.result?.artifacts as Record<string, string>) || {}).map((value) => String(value).replace('artifact://', ''))
}

export function mapRemoteAgentSnapshot(input: { binding: RemoteAgentTaskBinding; job: RemoteAgentJob; steps: RemoteAgentStep[]; events: RemoteAgentEvent[]; artifacts: Record<string, string>; adaptedResult: RemoteAgentAdaptedResult; workers?: RemoteAgentWorker[] }): AgentPresentationSnapshot {
  const planSteps = plannedSteps(input.job)
  const selectedTools = [...new Set([...planSteps.map((step) => step.tool), ...input.steps.map((step) => step.tool)])]
  const completeCount = input.steps.filter((step) => step.status === 'succeeded').length
  const expertProgress = input.steps.length ? input.steps.reduce((sum, step) => sum + (step.status === 'succeeded' ? 100 : step.progress <= 1 ? step.progress * 100 : step.progress), 0) / input.steps.length : 0
  const progress = input.job.status === 'succeeded' ? 100 : input.job.plan ? Math.round(20 + expertProgress * 0.8) : input.job.status === 'planning' ? 12 : 4
  const artifacts = input.adaptedResult.artifacts
  const onlineTools = new Set((input.workers || []).flatMap((worker) => worker.capabilities))
  const languageResult = input.adaptedResult.languageResult
  const semanticResult = input.adaptedResult.semanticResult
  const geometryResult = input.adaptedResult.geometryResult
  const action = record(input.job.plan?.action)
  const actionType = action?.type === 'workflow' || action?.type === 'tool_call' || action?.type === 'clarification' || action?.type === 'abstain' || action?.type === 'direct_answer' ? action.type : input.steps.length > 1 ? 'workflow' : 'tool_call'
  const plannerStep = { stepId: 'natural-language-planner', title: '自然语言任务规划', capabilityId: 'planner', capabilityName: '任务规划智能体', dependsOn: [] as string[], status: (input.job.plan ? 'completed' : input.job.status === 'planning' ? 'running' : 'pending') as AgentWorkflowStepStatus, summary: input.job.plan ? `已理解任务目标并生成“${String(input.job.plan.intent || '智能分析')}”协作路径` : input.job.status === 'planning' ? '正在理解任务目标、资产条件与专家能力' : '等待规划任务调度', artifactRefs: [] as string[], warnings: [] as string[], origin: 'planner' as const, executor: input.job.lease_owner || undefined }
  const consumedRuntime = new Set<number>()
  const matchedPlannedSteps = planSteps.map((planned) => {
    let runtimeIndex = input.steps.findIndex((step, index) => !consumedRuntime.has(index) && step.step_id === planned.stepId)
    if (runtimeIndex < 0) runtimeIndex = input.steps.findIndex((step, index) => !consumedRuntime.has(index) && step.tool === planned.tool)
    const step = runtimeIndex >= 0 ? input.steps[runtimeIndex] : undefined
    if (runtimeIndex >= 0) consumedRuntime.add(runtimeIndex)
    return {
      stepId: planned.stepId,
      title: toolNames[planned.tool] || planned.tool,
      capabilityId: planned.tool,
      capabilityName: toolNames[planned.tool] || planned.tool,
      dependsOn: planned.dependsOn.length ? planned.dependsOn : ['natural-language-planner'],
      status: step ? stepStatus(step.status) : 'pending' as AgentWorkflowStepStatus,
      summary: step ? runtimeSummary(step) : '已进入执行计划，等待前置条件满足后调度',
      artifactRefs: runtimeArtifacts(step),
      warnings: step?.status === 'lost' ? ['专家节点连接中断，等待恢复'] : [],
      origin: 'planned' as const,
      executor: step?.worker_id || undefined,
      verificationPolicy: planned.verificationPolicy,
    }
  })
  const runtimeAddedSteps = input.steps.flatMap((step, index) => {
    if (consumedRuntime.has(index)) return []
    const resultArguments = record(step.result?.arguments)
    const sourceTool = typeof resultArguments?.source_tool === 'string' ? resultArguments.source_tool : undefined
    const sourceStep = [...matchedPlannedSteps].reverse().find((item) => item.capabilityId === sourceTool)
      || matchedPlannedSteps.at(-1)
    const isVerification = step.tool === 'result_quality_verification'
    return [{
      stepId: step.step_id,
      title: toolNames[step.tool] || step.tool,
      capabilityId: step.tool,
      capabilityName: isVerification ? '可信结果质量门禁' : toolNames[step.tool] || step.tool,
      dependsOn: [sourceStep?.stepId || 'natural-language-planner'],
      status: stepStatus(step.status),
      summary: runtimeSummary(step),
      artifactRefs: runtimeArtifacts(step),
      warnings: step.status === 'lost' ? ['专家节点连接中断，等待恢复'] : [],
      origin: isVerification ? 'verification' as const : 'runtime' as const,
      executor: step.worker_id || undefined,
    }]
  })
  const fallbackRuntimeSteps = planSteps.length ? [] : input.steps.map((step, index) => ({
    stepId: step.step_id,
    title: toolNames[step.tool] || step.tool,
    capabilityId: step.tool,
    capabilityName: toolNames[step.tool] || step.tool,
    dependsOn: [index ? input.steps[index - 1].step_id : 'natural-language-planner'],
    status: stepStatus(step.status),
    summary: runtimeSummary(step),
    artifactRefs: runtimeArtifacts(step),
    warnings: step.status === 'lost' ? ['专家节点连接中断，等待恢复'] : [],
    origin: step.tool === 'result_quality_verification' ? 'verification' as const : 'runtime' as const,
    executor: step.worker_id || undefined,
  }))
  const expertSteps = planSteps.length ? [...matchedPlannedSteps, ...runtimeAddedSteps] : fallbackRuntimeSteps
  const evidenceSummary = languageResult
    ? languageResult.noTarget
      ? `语言专家已完成${languageResult.taskTypeLabel}，当前场景未发现符合条件的目标`
      : `语言专家已完成${languageResult.taskTypeLabel}${languageResult.selectedPoints === undefined ? '' : `，定位 ${languageResult.selectedPoints.toLocaleString('zh-CN')} 个目标点`}`
    : semanticResult
      ? `已完成${semanticResult.modeLabel}${semanticResult.numPresentClasses === undefined ? '' : `，识别 ${semanticResult.numPresentClasses} 类场景要素`}`
      : geometryResult
        ? `已完成${geometryResult.operationLabel}，${geometryResult.outcomeLabel}`
        : undefined
  return {
    schemaVersion: 'agent-presentation.v2', snapshotId: input.job.job_id, scenarioId: `remote:${input.job.job_id}`, sequence: input.job.version, status: executionStatus(input.job.status),
    task: { taskId: input.binding.taskId, taskText: input.binding.taskText, sceneId: input.binding.sceneId, normalizedTarget: input.binding.taskText, objective: input.binding.taskText, spatialConstraints: [], requiredAssets: Object.keys(input.job.submission.assets), availableAssets: Object.keys(input.job.submission.assets), missingAssets: [] },
    decision: { type: actionType, title: input.job.status === 'planning' ? '正在理解任务并规划专家协作' : '自然语言执行计划', summary: input.job.plan ? `已识别“${String(input.job.plan.intent || '智能分析')}”意图，正在按依赖关系调度专家。` : '任务已提交，等待规划智能体生成执行计划。', selectedTools, missingInputs: Array.isArray(action?.missing_fields) ? action.missing_fields.map(String) : [], reviewRequired: input.job.status === 'blocked_expert' },
    capabilities: AGENT_CAPABILITIES.map((item) => ({ ...item, status: onlineTools.size ? onlineTools.has(item.capabilityId) ? 'available' : 'unavailable' : item.status })),
    workflow: { workflowId: input.job.job_id, title: '自然语言驱动的 Agent 工作流', summary: input.job.plan ? `${completeCount} / ${Math.max(input.steps.length, planSteps.length)} 个专家步骤已完成${runtimeAddedSteps.length ? `，运行时增强 ${runtimeAddedSteps.length} 步` : ''}` : '规划智能体正在生成动态执行路径', progress, steps: [plannerStep, ...expertSteps] },
    evidence: { status: artifacts.length ? input.adaptedResult.regions.length || languageResult || semanticResult || geometryResult ? 'ready' : 'limited' : input.job.status === 'executing' ? 'collecting' : 'pending', summary: input.adaptedResult.regions.length ? `已从真实专家产物中提取 ${input.adaptedResult.regions.length} 个证据区域` : evidenceSummary || (artifacts.length ? `已生成 ${artifacts.length} 项真实专家产物，当前结果未形成风险区域` : '等待专家生成结果产物'), artifacts, regions: input.adaptedResult.regions, languageResult, semanticResult, geometryResult },
    quality: input.job.status === 'blocked_expert' ? { verdict: 'unavailable', checks: [], warnings: ['目标专家当前不可用'] } : input.adaptedResult.quality,
    spatial: input.adaptedResult.spatial,
    business: input.adaptedResult.business,
    response: input.job.status === 'blocked_expert' ? { kind: 'abstention', title: '等待专家能力恢复', content: String(input.job.error?.message || '没有在线 Worker 支持本次任务所需能力。'), evidenceSummary: [], suggestedActions: ['检查 Worker 状态', '能力恢复后重试任务'] } : actionType === 'clarification' ? { kind: 'clarification', title: '需要补充任务输入', content: String(action?.question || '请补充完成分析所需的数据。'), evidenceSummary: [], suggestedActions: ['返回任务发起页补充数据'] } : actionType === 'abstain' ? { kind: 'abstention', title: '当前任务无法安全执行', content: String(action?.reason || '现有能力不足以完成该任务。'), evidenceSummary: [], suggestedActions: ['调整任务描述或补充数据'] } : actionType === 'direct_answer' ? { kind: 'answer', title: '任务回答', content: String(action?.answer || ''), evidenceSummary: [], suggestedActions: [] } : undefined,
    trace: input.events.map(mapRemoteAgentEvent),
    errors: input.job.error ? [{ code: input.job.status === 'blocked_expert' ? 'CAPABILITY_OFFLINE' : 'EXECUTION_FAILED', title: input.job.status === 'blocked_expert' ? '专家能力不可用' : '执行失败', message: String(input.job.error.message || input.job.error.code || 'Agent 任务执行失败'), retryable: true, traceId: input.job.trace_id }] : [], createdAt: input.job.created_at,
  }
}
