<script setup lang="ts">
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { AgentDemoScenario } from '@/lib/agent-presentation-types'

defineProps<{ scenario?: AgentDemoScenario | null }>()
</script>

<template>
  <section class="rounded-2xl border border-white/[0.08] bg-card/60 p-5 shadow-card">
    <div class="flex items-center gap-2">
      <span class="grid h-7 w-7 place-items-center rounded-lg bg-primary/10 text-xs font-semibold text-primary">3</span>
      <div><h2 class="text-sm font-semibold text-foreground">确认智能规划</h2><p class="mt-0.5 text-[11px] text-muted-foreground">这里只显示即将执行的核心路径</p></div>
    </div>
    <div v-if="scenario" class="mt-4 flex flex-wrap items-center gap-2">
      <template v-for="(step, index) in scenario.timeline[0].snapshot.workflow?.steps" :key="step.stepId">
        <div class="flex items-center gap-2">
          <span class="inline-flex items-center gap-2 rounded-xl border border-white/[0.08] bg-black/10 px-3 py-2 text-xs text-card-foreground"><SafeIcon :name="index === 0 ? 'ScanSearch' : 'Boxes'" :size="14" class="text-primary"/>{{ step.title }}</span>
          <SafeIcon v-if="index < (scenario.timeline[0].snapshot.workflow?.steps.length || 1) - 1" name="ArrowRight" :size="14" class="text-primary/50"/>
        </div>
      </template>
    </div>
    <div v-else class="mt-4 flex items-center gap-3 rounded-xl border border-dashed border-white/[0.1] bg-black/10 px-4 py-3 text-xs text-muted-foreground"><SafeIcon name="Sparkles" :size="16" class="text-primary"/>提交后，Agent 将依据任务目标和数据条件生成动态执行路径。</div>
  </section>
</template>
