import {
  agentDemoScenarios,
  getAgentDemoScenario,
  getDefaultAgentDemoScenario,
} from '@/data/agent-demo/scenarios'
import type { AgentDemoScenario, AgentTaskInput } from '@/lib/agent-presentation-types'

function normalizeText(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, '')
}

function scoreScenario(taskText: string, scenario: AgentDemoScenario): number {
  const normalizedTask = normalizeText(taskText)
  if (!normalizedTask) return 0

  const exactTask = normalizeText(scenario.taskText)
  if (normalizedTask === exactTask) return 1000

  return scenario.aliases.reduce((score, alias) => {
    const normalizedAlias = normalizeText(alias)
    return normalizedAlias && normalizedTask.includes(normalizedAlias)
      ? score + Math.max(1, normalizedAlias.length)
      : score
  }, 0)
}

export function matchAgentDemoScenario(input: AgentTaskInput): AgentDemoScenario {
  if (input.scenarioId) {
    const explicitScenario = getAgentDemoScenario(input.scenarioId)
    if (explicitScenario) return explicitScenario
  }

  const ranked = agentDemoScenarios
    .map((scenario) => ({ scenario, score: scoreScenario(input.taskText, scenario) }))
    .sort((left, right) => right.score - left.score)

  return ranked[0]?.score > 0 ? ranked[0].scenario : getDefaultAgentDemoScenario()
}
