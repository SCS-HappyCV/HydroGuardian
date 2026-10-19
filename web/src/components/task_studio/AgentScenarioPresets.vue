<script setup lang="ts">
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentDecisionType, AgentDemoScenario } from '@/lib/agent-presentation-types'

defineProps<{
  scenarios: AgentDemoScenario[]
  selectedScenarioId?: string
  disabled?: boolean
}>()

defineEmits<{
  select: [scenario: AgentDemoScenario]
}>()

const decisionMeta: Record<AgentDecisionType, { label: string; icon: string; tone: string }> = {
  workflow: { label: '专家协同', icon: 'Network', tone: 'text-primary border-primary/20 bg-primary/[0.07]' },
  tool_call: { label: '单项分析', icon: 'Ruler', tone: 'text-violet-300 border-violet-400/20 bg-violet-400/[0.07]' },
  direct_answer: { label: '直接回答', icon: 'MessageCircle', tone: 'text-accent border-accent/20 bg-accent/[0.07]' },
  clarification: { label: '补充信息', icon: 'MessageSquareMore', tone: 'text-amber-300 border-amber-400/20 bg-amber-400/[0.07]' },
  abstain: { label: '安全判断', icon: 'ShieldAlert', tone: 'text-rose-300 border-rose-400/20 bg-rose-400/[0.07]' },
}
</script>

<template>
  <section class="surface-base card-padding space-y-3">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h3 class="text-item-title flex items-center gap-2">
          <SafeIcon name="Sparkles" :size="18" class="text-accent" />
          Agent 决策示例
        </h3>
        <p class="mt-1 text-xs text-muted-foreground">以下示例用于体验不同决策路径，也可以直接输入自己的巡查任务</p>
      </div>
      <span class="rounded-full border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[10px] text-muted-foreground">决策示例</span>
    </div>

    <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
      <button
        v-for="scenario in scenarios"
        :key="scenario.scenarioId"
        type="button"
        class="group min-w-0 rounded-xl border p-3 text-left transition-all disabled:cursor-not-allowed disabled:opacity-50"
        :class="scenario.scenarioId === selectedScenarioId
          ? 'border-primary/45 bg-primary/[0.09] shadow-[0_0_24px_hsl(var(--primary)/.08)]'
          : 'border-white/[0.07] bg-black/10 hover:border-white/[0.14] hover:bg-white/[0.03]'"
        :disabled="disabled"
        @click="$emit('select', scenario)"
      >
        <span class="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px]" :class="decisionMeta[scenario.decisionType].tone">
          <SafeIcon :name="decisionMeta[scenario.decisionType].icon" :size="12" />
          {{ decisionMeta[scenario.decisionType].label }}
        </span>
        <strong class="mt-2.5 block truncate text-xs font-semibold text-card-foreground">{{ scenario.title }}</strong>
        <p class="mt-1 line-clamp-2 min-h-8 text-[10px] leading-4 text-muted-foreground">{{ scenario.taskText }}</p>
      </button>
    </div>
  </section>
</template>
