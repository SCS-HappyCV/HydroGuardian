<script setup lang="ts">
import { computed } from 'vue'
import type { WorkorderData } from '@/data/WorkorderData'
import type { WorkorderTimelineVO } from '@/data/WorkorderTimelineService'
import type { WorkorderEvidenceData } from '@/data/WorkorderEvidenceData'
import type { WorkorderReviewVO } from '@/data/WorkorderReviewService'
import { buildClosureStages } from '@/lib/workorder-closure'
import SafeIcon from '@/components/common/SafeIcon.vue'

interface Props {
  workorder: WorkorderData
  timeline: WorkorderTimelineVO[]
  evidence?: WorkorderEvidenceData[]
  review?: WorkorderReviewVO | null
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  evidence: () => [],
  review: null,
  compact: false,
})

const stages = computed(() => buildClosureStages(props.workorder, props.timeline, props.evidence, props.review))
const completedCount = computed(() => stages.value.filter((stage) => stage.status === 'completed').length)

function formatTime(value?: string): string {
  if (!value) return '等待流转'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <section class="rounded-2xl border border-border/60 bg-card/40 p-4">
    <div class="flex items-center justify-between gap-3">
      <div>
        <h3 class="flex items-center gap-2 text-sm font-semibold text-foreground">
          <SafeIcon name="Route" :size="16" class="text-cyan-400" />
          AI 风险处置闭环
        </h3>
        <p class="mt-1 text-[11px] text-muted-foreground">从智能发现到复核关闭，全流程证据可追溯</p>
      </div>
      <span class="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-[11px] font-semibold text-cyan-300">
        {{ completedCount }}/5 已完成
      </span>
    </div>

    <div v-if="compact" class="mt-4 space-y-0">
      <div v-for="(stage, index) in stages" :key="stage.id" class="flex gap-3">
        <div class="flex flex-col items-center">
          <span
            class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border"
            :class="stage.status === 'completed'
              ? 'border-cyan-300/40 bg-cyan-300/15 text-cyan-300'
              : stage.status === 'current'
                ? 'border-amber-300/50 bg-amber-300/15 text-amber-300 animate-pulse'
                : 'border-border bg-muted/30 text-muted-foreground'"
          >
            <SafeIcon :name="stage.status === 'completed' ? 'Check' : stage.icon" :size="12" />
          </span>
          <span v-if="index < stages.length - 1" class="h-10 w-px" :class="stage.status === 'completed' ? 'bg-cyan-300/35' : 'bg-border/50'" />
        </div>
        <div class="min-w-0 flex-1 pb-3">
          <div class="flex items-center justify-between gap-2">
            <strong class="text-xs text-foreground">{{ stage.label }}</strong>
            <span class="whitespace-nowrap text-[10px] text-muted-foreground">{{ formatTime(stage.time) }}</span>
          </div>
          <p class="mt-1 line-clamp-2 text-[10px] leading-relaxed text-muted-foreground">{{ stage.note }}</p>
        </div>
      </div>
    </div>

    <div v-else class="mt-5">
      <div class="grid grid-cols-5">
        <div v-for="(stage, index) in stages" :key="stage.id" class="relative flex flex-col items-center text-center">
          <div
            v-if="index > 0"
            class="absolute right-1/2 top-5 h-px w-full"
            :class="stage.status === 'completed' ? 'bg-cyan-300/45' : 'bg-border/60'"
          />
          <span
            class="relative z-10 flex h-10 w-10 items-center justify-center rounded-full border-2 shadow-[0_0_18px_rgba(0,0,0,.2)]"
            :class="stage.status === 'completed'
              ? 'border-cyan-300/50 bg-[#0b3b49] text-cyan-200'
              : stage.status === 'current'
                ? 'border-amber-300/60 bg-amber-300/15 text-amber-200 animate-pulse'
                : 'border-border bg-card text-muted-foreground'"
          >
            <SafeIcon :name="stage.status === 'completed' ? 'Check' : stage.icon" :size="17" />
          </span>
          <strong class="mt-2 text-xs" :class="stage.status === 'pending' ? 'text-muted-foreground' : 'text-foreground'">{{ stage.shortLabel }}</strong>
          <span class="mt-1 text-[9px] text-muted-foreground">{{ formatTime(stage.time) }}</span>
        </div>
      </div>

      <div class="mt-5 grid gap-2 lg:grid-cols-5">
        <article
          v-for="stage in stages"
          :key="`${stage.id}-detail`"
          class="rounded-xl border p-3"
          :class="stage.status === 'completed'
            ? 'border-cyan-300/15 bg-cyan-300/[0.035]'
            : stage.status === 'current'
              ? 'border-amber-300/20 bg-amber-300/[0.04]'
              : 'border-border/40 bg-muted/10'"
        >
          <div class="text-[10px] font-medium text-foreground">{{ stage.actor || '等待执行' }}</div>
          <p class="mt-1.5 text-[10px] leading-relaxed text-muted-foreground">{{ stage.note }}</p>
          <div v-if="stage.evidence" class="mt-2 flex items-start gap-1 text-[9px] leading-relaxed text-cyan-300/80">
            <SafeIcon name="Paperclip" :size="10" class="mt-0.5 shrink-0" />
            {{ stage.evidence }}
          </div>
        </article>
      </div>
    </div>
  </section>
</template>
