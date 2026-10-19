import type { AgentDecisionView } from '@/lib/agent-presentation-types'
import { createScenario, createTrace } from './scenario-builder'

const decision: AgentDecisionView = {
  type: 'abstain',
  title: '当前条件不足，建议补采或人工复核',
  summary: '新增施工扰动需要前后时相对比，但当前场景只有当前影像，无法形成可靠结论。',
  reasonCode: 'MISSING_PRE_IMAGE',
  selectedTools: [],
  missingInputs: ['前时相影像'],
  reviewRequired: true,
}

export const abstainScenario = createScenario({
  scenarioId: 'missing-temporal-asset-abstention',
  title: '时相数据不足安全停止',
  description: '缺少关键数据时不强行输出变化结论。',
  task: {
    taskId: 'task-agent-abstain-001',
    taskText: '判断该岸段是否出现了新增施工扰动',
    sceneId: 'scene-current-image-only-001',
    normalizedTarget: '岸段新增施工扰动',
    objective: '通过前后时相变化判断是否出现新增施工活动',
    spatialConstraints: ['限定当前岸段范围'],
    requiredAssets: ['前时相影像', '后时相影像'],
    availableAssets: ['后时相影像'],
    missingAssets: ['前时相影像'],
  },
  decisionType: 'abstain',
  aliases: ['新增施工', '是否新增', '变化判断', '只有当前影像', '缺少前时相'],
  finalRoute: './task-execution-monitor.html?taskId=task-agent-abstain-001',
  snapshots: [
    {
      sequence: 0,
      atMs: 0,
      status: 'preparing',
      decision,
      trace: [createTrace('trace-abstain-00', 'agent.asset_check', '正在检查时相变化分析所需资产')],
    },
    {
      sequence: 1,
      atMs: 800,
      status: 'abstained',
      decision,
      response: {
        kind: 'abstention',
        title: '当前无法可靠判断新增扰动',
        content: '场景缺少前时相影像，无法完成同一区域的前后变化对比。系统未强行生成风险结论。',
        evidenceSummary: ['当前影像可用', '前时相影像缺失', '未执行变化检测'],
        suggestedActions: ['补充前时相影像', '转人工现场核验', '改为分析当前场景几何异常'],
      },
      evidence: {
        status: 'unavailable',
        summary: '缺少关键时相资产，未生成变化证据',
      },
      quality: {
        verdict: 'unavailable',
        checks: [{ checkId: 'temporal-assets', label: '时相资产完整性', status: 'failed', summary: '缺少前时相影像' }],
        warnings: ['无法执行前后时相变化检测'],
        recommendedAction: '补充前时相影像或转人工核验',
      },
      trace: [createTrace('trace-abstain-01', 'agent.abstain', '关键时相资产不足，分析已安全停止', 'warning')],
    },
  ],
})
