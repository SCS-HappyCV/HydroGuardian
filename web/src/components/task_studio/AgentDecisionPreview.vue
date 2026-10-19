<script setup lang="ts">
import { computed } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import type {
  AgentDecisionType,
  AgentDemoScenario,
  AgentPresentationSnapshot,
  AgentResponseOption,
} from '@/lib/agent-presentation-types'

const props = defineProps<{
  scenario?: AgentDemoScenario | null
  result?: AgentPresentationSnapshot | null
}>()

defineEmits<{
  applyOption: [option: AgentResponseOption]
}>()

const previewSnapshot = computed(() => props.scenario?.timeline[0]?.snapshot)
const decision = computed(() => props.result?.decision ?? previewSnapshot.value?.decision)
const task = computed(() => props.result?.task ?? previewSnapshot.value?.task)
const response = computed(() => props.result?.response)

const decisionMeta: Record<AgentDecisionType, { label: string; icon: string; tone: string }> = {
  workflow: { label: '多专家协同分析', icon: 'Network', tone: 'text-primary border-primary/20 bg-primary/[0.07]' },
  tool_call: { label: '单项专家分析', icon: 'Wrench', tone: 'text-violet-300 border-violet-400/20 bg-violet-400/[0.07]' },
  direct_answer: { label: '直接形成回答', icon: 'MessageCircle', tone: 'text-accent border-accent/20 bg-accent/[0.07]' },
  clarification: { label: '需要补充信息', icon: 'MessageSquareMore', tone: 'text-amber-300 border-amber-400/20 bg-amber-400/[0.07]' },
  abstain: { label: '当前条件不足', icon: 'ShieldAlert', tone: 'text-rose-300 border-rose-400/20 bg-rose-400/[0.07]' },
}

const selectedCapabilityNames = computed(() => {
  const snapshot = props.result ?? previewSnapshot.value
  if (!snapshot || !decision.value) return []
  return decision.value.selectedTools.map((toolId) => {
    return snapshot.capabilities.find((item) => item.capabilityId === toolId)?.name ?? toolId
  })
})
</script>

<template>
  <section v-if="decision && task" class="overflow-hidden rounded-2xl border border-white/[0.08] bg-card/65 shadow-card">
    <header class="flex items-start justify-between gap-3 border-b border-white/[0.07] p-4">
      <div>
        <div class="flex items-center gap-2 text-sm font-semibold text-foreground">
          <SafeIcon name="Route" :size="17" class="text-primary" />
          Agent 决策预检
        </div>
        <p class="mt-1 text-[11px] text-muted-foreground">根据任务目标与场景条件选择处理方式</p>
      </div>
      <span class="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px]" :class="decisionMeta[decision.type].tone">
        <SafeIcon :name="decisionMeta[decision.type].icon" :size="12" />
        {{ decisionMeta[decision.type].label }}
      </span>
    </header>

    <div class="space-y-4 p-4">
      <div>
        <p class="text-sm font-medium leading-6 text-card-foreground">{{ decision.title }}</p>
        <p class="mt-1 text-xs leading-5 text-muted-foreground">{{ decision.summary }}</p>
      </div>

      <div class="grid grid-cols-2 gap-2 text-[11px]">
        <div class="rounded-lg border border-white/[0.06] bg-black/10 p-3">
          <span class="text-muted-foreground">识别目标</span>
          <strong class="mt-1 block truncate font-medium text-card-foreground">{{ task.normalizedTarget }}</strong>
        </div>
        <div class="rounded-lg border border-white/[0.06] bg-black/10 p-3">
          <span class="text-muted-foreground">场景数据</span>
          <strong class="mt-1 block font-medium text-card-foreground">{{ task.availableAssets.length }} 类可用</strong>
        </div>
      </div>

      <div v-if="selectedCapabilityNames.length" class="space-y-2">
        <p class="flex items-center gap-1.5 text-[11px] text-muted-foreground"><SafeIcon name="Blocks" :size="13" />计划调用能力</p>
        <div class="flex flex-wrap gap-1.5">
          <span v-for="name in selectedCapabilityNames" :key="name" class="rounded-md border border-primary/15 bg-primary/[0.06] px-2 py-1 text-[10px] text-card-foreground">{{ name }}</span>
        </div>
      </div>

      <div v-if="task.missingAssets.length || decision.missingInputs.length" class="rounded-xl border border-amber-400/15 bg-amber-400/[0.05] p-3">
        <p class="flex items-center gap-1.5 text-[11px] font-medium text-amber-200"><SafeIcon name="Info" :size="13" />需要补充</p>
        <div class="mt-2 flex flex-wrap gap-1.5">
          <span v-for="item in [...task.missingAssets, ...decision.missingInputs]" :key="item" class="rounded-md bg-amber-300/10 px-2 py-1 text-[10px] text-amber-100">{{ item }}</span>
        </div>
      </div>

      <div v-if="response" class="rounded-xl border border-accent/20 bg-accent/[0.06] p-4">
        <p class="flex items-center gap-2 text-sm font-semibold text-card-foreground">
          <SafeIcon :name="response.kind === 'abstention' ? 'ShieldCheck' : response.kind === 'clarification' ? 'MessageSquareMore' : 'BadgeCheck'" :size="16" class="text-accent" />
          {{ response.title }}
        </p>
        <p class="mt-2 text-xs leading-5 text-muted-foreground">{{ response.content }}</p>
        <div v-if="response.options?.length" class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="option in response.options"
            :key="option.optionId"
            type="button"
            class="rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5 text-[10px] text-card-foreground transition-colors hover:border-accent/30 hover:bg-accent/[0.07]"
            @click="$emit('applyOption', option)"
          >
            {{ option.label }}
          </button>
        </div>
        <div v-if="response.suggestedActions.length" class="mt-3 border-t border-white/[0.07] pt-3 text-[10px] text-muted-foreground">
          下一步：{{ response.suggestedActions.join(' · ') }}
        </div>
      </div>
    </div>
  </section>
</template>
