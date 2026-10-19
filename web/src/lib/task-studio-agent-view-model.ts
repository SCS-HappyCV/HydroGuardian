import type {
  AgentDecisionType,
  AgentDemoScenario,
  AgentPresentationSnapshot,
} from '@/lib/agent-presentation-types'

export type TaskStudioPageState =
  | 'empty'
  | 'plan_ready'
  | 'submitting'
  | 'direct_answer_ready'
  | 'clarification_required'
  | 'abstain_ready'

export interface TaskStudioAgentViewModel {
  pageState: TaskStudioPageState
  decisionType?: AgentDecisionType
  decisionTitle: string
  decisionSummary: string
  actionLabel: string
  statusLabel: string
  selectedToolCount: number
  reviewRequired: boolean
}

const ACTION_LABELS: Record<AgentDecisionType, string> = {
  workflow: '启动智能分析',
  tool_call: '执行空间计算',
  direct_answer: '查看场景回答',
  clarification: '补充任务信息',
  abstain: '查看补充建议',
}

export function buildTaskStudioAgentViewModel(
  scenario: AgentDemoScenario | null | undefined,
  snapshot: AgentPresentationSnapshot | null | undefined,
  isSubmitting: boolean,
): TaskStudioAgentViewModel {
  if (!scenario && !snapshot) {
    return {
      pageState: 'empty',
      decisionTitle: '等待任务输入',
      decisionSummary: '描述巡查目标后，Agent 将检查场景并生成处理计划。',
      actionLabel: '开始任务理解',
      statusLabel: '等待任务',
      selectedToolCount: 0,
      reviewRequired: false,
    }
  }

  const decision = snapshot?.decision ?? scenario?.timeline[0].snapshot.decision
  const type = decision?.type
  let pageState: TaskStudioPageState = isSubmitting ? 'submitting' : 'plan_ready'
  if (!isSubmitting && snapshot?.status === 'completed' && type === 'direct_answer') pageState = 'direct_answer_ready'
  if (!isSubmitting && snapshot?.status === 'clarification_required') pageState = 'clarification_required'
  if (!isSubmitting && snapshot?.status === 'abstained') pageState = 'abstain_ready'

  return {
    pageState,
    decisionType: type,
    decisionTitle: decision?.title ?? 'Agent 计划已生成',
    decisionSummary: decision?.summary ?? '',
    actionLabel: type ? ACTION_LABELS[type] : '启动智能分析',
    statusLabel: pageState === 'submitting'
      ? '正在创建任务'
      : pageState === 'clarification_required'
        ? '需要补充'
        : pageState === 'abstain_ready'
          ? '条件不足'
          : '计划就绪',
    selectedToolCount: decision?.selectedTools.length ?? 0,
    reviewRequired: Boolean(decision?.reviewRequired || snapshot?.quality.verdict === 'review_required'),
  }
}
