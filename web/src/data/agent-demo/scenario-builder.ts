import { cloneAgentCapabilities } from '@/lib/agent-capability-catalog'
import type {
  AgentBusinessView,
  AgentDecisionType,
  AgentDecisionView,
  AgentDemoScenario,
  AgentEvidenceView,
  AgentExecutionStatus,
  AgentPresentationSnapshot,
  AgentQualityView,
  AgentResponseView,
  AgentTaskView,
  AgentTraceView,
  AgentWorkflowView,
} from '@/lib/agent-presentation-types'

export const DEMO_TIMESTAMP = '2026-07-31T09:00:00+08:00'

export interface ScenarioSnapshotInput {
  sequence: number
  atMs: number
  status: AgentExecutionStatus
  decision: AgentDecisionView
  workflow?: AgentWorkflowView
  response?: AgentResponseView
  evidence?: Partial<AgentEvidenceView>
  quality?: Partial<AgentQualityView>
  business?: Partial<AgentBusinessView>
  trace?: AgentTraceView[]
}

export interface ScenarioDefinitionInput {
  scenarioId: string
  title: string
  description: string
  task: AgentTaskView
  decisionType: AgentDecisionType
  aliases: string[]
  snapshots: ScenarioSnapshotInput[]
  finalRoute: string
}

const EMPTY_EVIDENCE: AgentEvidenceView = {
  status: 'pending',
  summary: '正在等待专家分析产物',
  artifacts: [],
  regions: [],
}

const EMPTY_QUALITY: AgentQualityView = {
  verdict: 'unavailable',
  checks: [],
  warnings: [],
}

const EMPTY_BUSINESS: AgentBusinessView = {
  risks: [],
  recommendations: [],
  workOrders: [],
}

export function createTrace(
  traceId: string,
  stage: string,
  message: string,
  level: AgentTraceView['level'] = 'info',
): AgentTraceView {
  return { traceId, stage, message, level, timestamp: DEMO_TIMESTAMP }
}

export function createScenario(input: ScenarioDefinitionInput): AgentDemoScenario {
  return {
    scenarioId: input.scenarioId,
    title: input.title,
    description: input.description,
    taskText: input.task.taskText,
    decisionType: input.decisionType,
    aliases: input.aliases,
    finalRoute: input.finalRoute,
    timeline: input.snapshots.map((item) => ({
      atMs: item.atMs,
      snapshot: createSnapshot(input.scenarioId, input.task, item),
    })),
  }
}

function createSnapshot(
  scenarioId: string,
  task: AgentTaskView,
  input: ScenarioSnapshotInput,
): AgentPresentationSnapshot {
  return {
    schemaVersion: 'agent-presentation.v2',
    snapshotId: `${scenarioId}-snapshot-${input.sequence}`,
    scenarioId,
    sequence: input.sequence,
    status: input.status,
    task: { ...task },
    decision: {
      ...input.decision,
      selectedTools: [...input.decision.selectedTools],
      missingInputs: [...input.decision.missingInputs],
    },
    capabilities: cloneAgentCapabilities(),
    workflow: input.workflow,
    response: input.response,
    evidence: {
      ...EMPTY_EVIDENCE,
      ...input.evidence,
      artifacts: input.evidence?.artifacts ?? [],
      regions: input.evidence?.regions ?? [],
    },
    quality: {
      ...EMPTY_QUALITY,
      ...input.quality,
      checks: input.quality?.checks ?? [],
      warnings: input.quality?.warnings ?? [],
    },
    business: {
      ...EMPTY_BUSINESS,
      ...input.business,
      risks: input.business?.risks ?? [],
      recommendations: input.business?.recommendations ?? [],
      workOrders: input.business?.workOrders ?? [],
    },
    trace: input.trace ?? [],
    errors: [],
    createdAt: DEMO_TIMESTAMP,
  }
}
