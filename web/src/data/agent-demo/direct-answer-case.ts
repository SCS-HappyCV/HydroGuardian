import type { AgentDecisionView } from '@/lib/agent-presentation-types'
import { createScenario, createTrace } from './scenario-builder'

const decision: AgentDecisionView = {
  type: 'direct_answer',
  title: '已具备直接回答条件',
  summary: '问题只涉及已登记的场景资产和能力范围，无需调用分析专家。',
  reasonCode: 'SCENE_METADATA_QUERY',
  selectedTools: [],
  missingInputs: [],
  reviewRequired: false,
}

export const directAnswerScenario = createScenario({
  scenarioId: 'scene-assets-direct-answer',
  title: '预置场景数据能力查询',
  description: '直接回答当前场景的数据组成和支持能力。',
  task: {
    taskId: 'task-agent-answer-001',
    taskText: '当前预置场景包含哪些可用于研判的数据',
    sceneId: 'scene-riverbank-001',
    sampleId: 'sample-riverbank-001',
    normalizedTarget: '预置场景资产与可用能力',
    objective: '说明当前场景数据组成和可以支持的分析类型',
    spatialConstraints: [],
    requiredAssets: [],
    availableAssets: ['正射影像', '点云', '前时相影像', '后时相影像'],
    missingAssets: [],
  },
  decisionType: 'direct_answer',
  aliases: ['包含哪些数据', '场景数据', '有哪些资产', '支持哪些分析', '可用于研判'],
  finalRoute: './task-execution-monitor.html?taskId=task-agent-answer-001',
  snapshots: [
    {
      sequence: 0,
      atMs: 0,
      status: 'preparing',
      decision,
      trace: [createTrace('trace-answer-00', 'agent.understand', '正在读取当前场景资产摘要')],
    },
    {
      sequence: 1,
      atMs: 450,
      status: 'completed',
      decision,
      response: {
        kind: 'answer',
        title: '当前场景数据完整',
        content: '当前预置场景包含正射影像、点云、前时相影像和后时相影像，可支持场景语义、空间几何和前后变化分析。',
        evidenceSummary: ['正射影像：可用', '点云：可用', '前后时相影像：可用'],
        suggestedActions: ['发起综合风险筛查', '计算近水距离', '查看场景证据'],
      },
      evidence: {
        status: 'ready',
        summary: '已读取四类场景资产元数据',
      },
      quality: {
        verdict: 'passed',
        confidence: 1,
        uncertainty: 0,
        checks: [{ checkId: 'metadata', label: '场景元数据', status: 'passed', summary: '资产登记信息完整' }],
        warnings: [],
      },
      trace: [createTrace('trace-answer-01', 'agent.answer', '已根据场景元数据生成回答')],
    },
  ],
})
