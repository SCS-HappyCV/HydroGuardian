import type { AgentDemoScenario } from '@/lib/agent-presentation-types'
import { abstainScenario } from './abstain-case'
import { clarificationScenario } from './clarification-case'
import { directAnswerScenario } from './direct-answer-case'
import { toolScenario } from './tool-case'
import { workflowScenario } from './workflow-case'

export const DEFAULT_AGENT_DEMO_SCENARIO_ID = workflowScenario.scenarioId

export const agentDemoScenarios: AgentDemoScenario[] = [
  workflowScenario,
  toolScenario,
  directAnswerScenario,
  clarificationScenario,
  abstainScenario,
]

export function getAgentDemoScenario(scenarioId: string): AgentDemoScenario | undefined {
  return agentDemoScenarios.find((scenario) => scenario.scenarioId === scenarioId)
}

export function getDefaultAgentDemoScenario(): AgentDemoScenario {
  return workflowScenario
}
