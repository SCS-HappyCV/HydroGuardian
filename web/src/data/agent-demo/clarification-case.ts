import type { AgentDecisionView } from '@/lib/agent-presentation-types'
import { createScenario, createTrace } from './scenario-builder'

const decision: AgentDecisionView = {
  type: 'clarification',
  title: '需要补充任务信息',
  summary: '当前描述缺少明确场景范围和异常类型，补充后才能组织可靠的分析流程。',
  reasonCode: 'AMBIGUOUS_SCOPE_AND_TARGET',
  selectedTools: [],
  missingInputs: ['巡查场景范围', '需要关注的异常类型'],
  reviewRequired: false,
}

export const clarificationScenario = createScenario({
  scenarioId: 'ambiguous-task-clarification',
  title: '巡查任务信息补充',
  description: '当任务目标或范围不明确时，Agent 主动请求澄清。',
  task: {
    taskId: 'task-agent-clarification-001',
    taskText: '看一下这里最近有没有异常',
    sceneId: '',
    normalizedTarget: '待确认的场景异常',
    objective: '确认巡查范围和异常类型后生成分析计划',
    spatialConstraints: [],
    requiredAssets: [],
    availableAssets: [],
    missingAssets: ['场景范围'],
  },
  decisionType: 'clarification',
  aliases: ['看一下这里', '有没有异常', '这里最近', '帮我看看'],
  finalRoute: './task-studio.html?taskId=task-agent-clarification-001',
  snapshots: [
    {
      sequence: 0,
      atMs: 0,
      status: 'preparing',
      decision,
      trace: [createTrace('trace-clarify-00', 'agent.understand', '正在检查任务目标和场景信息')],
    },
    {
      sequence: 1,
      atMs: 700,
      status: 'clarification_required',
      decision,
      response: {
        kind: 'clarification',
        title: '请补充巡查范围和重点',
        content: '请选择需要分析的场景，并确认重点关注新增扰动、沟渠、岸坡还是进行综合筛查。',
        evidenceSummary: ['尚未选择场景', '异常目标描述较宽泛'],
        options: [
          { optionId: 'scope-standard', label: '使用当前预置场景', value: 'scene-riverbank-001' },
          { optionId: 'target-disturbance', label: '重点筛查新增扰动', value: 'near_water_disturbance' },
          { optionId: 'target-comprehensive', label: '执行综合筛查', value: 'comprehensive_inspection' },
        ],
        suggestedActions: ['选择场景', '明确异常类型', '重新生成分析计划'],
      },
      quality: {
        verdict: 'unavailable',
        checks: [{ checkId: 'task-completeness', label: '任务信息完整性', status: 'warning', summary: '缺少场景范围和明确目标' }],
        warnings: ['当前信息不足以选择专家能力'],
        recommendedAction: '补充信息后重新提交',
      },
      trace: [createTrace('trace-clarify-01', 'agent.clarification', '任务信息不足，已生成澄清问题', 'warning')],
    },
  ],
})
