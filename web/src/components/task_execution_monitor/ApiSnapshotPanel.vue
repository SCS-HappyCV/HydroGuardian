<!-- 智能体执行快照面板：展示真实执行返回的案例、风险、证据、链路和错误诊断。 -->
<script setup lang="ts">
import { computed } from 'vue'
import {
  buildAgentTimeline,
  getEvidenceStatusLabel,
  getExecutionStatusLabel,
  getPersistenceStatusLabel,
  getRiskLevelLabel,
} from '@/api/execution-display'
import type { TaskExecutionSnapshot } from '@/lib/api-contracts'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  snapshot: TaskExecutionSnapshot
}>()

// 根据后端风险等级生成前端徽标样式。
const riskLevelClass = computed(() => {
  const riskLevel = props.snapshot.riskLevel.trim().toUpperCase()
  if (riskLevel === 'HIGH') return 'border-red-500/40 bg-red-500/10 text-red-600'
  if (riskLevel === 'MEDIUM') return 'border-amber-500/40 bg-amber-500/10 text-amber-600'
  if (riskLevel === 'LOW') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-600'
  if (riskLevel === 'REVIEW_REQUIRED') return 'border-sky-500/40 bg-sky-500/10 text-sky-600'
  return 'border-muted-foreground/30 bg-muted/30 text-muted-foreground'
})

// 构建完整中文时间线，供最近链路和错误诊断复用。
const timelineEvents = computed(() => {
  return buildAgentTimeline(props.snapshot)
})

// 最近链路只展示末尾五条，完整链路在下方日志流中回放。
const recentEvents = computed(() => {
  return timelineEvents.value.slice(-5)
})

// 错误事件单独形成诊断面板，避免失败原因淹没在普通日志里。
const errorEvents = computed(() => {
  return timelineEvents.value.filter((event) => event.level === 'error')
})
</script>

<template>
  <section class="surface-base card-padding space-y-4">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 class="text-item-title flex items-center gap-2">
          <SafeIcon name="Cpu" :size="18" class="text-accent" />
          智能体执行快照
        </h2>
        <p class="text-sm text-muted-foreground mt-1">案例 ID：{{ snapshot.caseId || '未持久化' }}</p>
      </div>
      <span class="inline-flex w-fit items-center rounded-md border px-2.5 py-1 text-xs font-medium" :class="riskLevelClass">
        {{ getRiskLevelLabel(snapshot.riskLevel) }}
      </span>
    </div>

    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <div class="rounded-md border border-border/60 bg-muted/20 p-3">
        <p class="text-xs text-muted-foreground">风险分数</p>
        <p class="mt-1 text-lg font-semibold text-foreground">{{ snapshot.riskScore }}</p>
      </div>
      <div class="rounded-md border border-border/60 bg-muted/20 p-3">
        <p class="text-xs text-muted-foreground">执行状态</p>
        <p class="mt-1 text-lg font-semibold text-foreground">{{ getExecutionStatusLabel(snapshot.executionStatus) }}</p>
      </div>
      <div class="rounded-md border border-border/60 bg-muted/20 p-3">
        <p class="text-xs text-muted-foreground">证据状态</p>
        <p class="mt-1 text-lg font-semibold text-foreground">{{ getEvidenceStatusLabel(snapshot.evidenceStatus) }}</p>
      </div>
      <div class="rounded-md border border-border/60 bg-muted/20 p-3">
        <p class="text-xs text-muted-foreground">链路事件</p>
        <p class="mt-1 text-lg font-semibold text-foreground">{{ snapshot.traceTotal }}</p>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div class="rounded-md border border-border/60 bg-muted/20 p-3">
        <p class="text-xs text-muted-foreground">推荐动作</p>
        <p class="mt-2 text-sm text-foreground leading-relaxed">{{ snapshot.recommendationAction || '暂无建议' }}</p>
      </div>
      <div class="rounded-md border border-border/60 bg-muted/20 p-3">
        <p class="text-xs text-muted-foreground">持久化状态</p>
        <p class="mt-2 text-sm text-foreground leading-relaxed">
          {{ getPersistenceStatusLabel(snapshot.casePersistenceStatus) }}
          <span v-if="snapshot.casePersistenceError" class="text-destructive"> · {{ snapshot.casePersistenceError }}</span>
        </p>
      </div>
    </div>

    <div v-if="errorEvents.length" class="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-2">
      <div class="flex items-center gap-2 text-sm font-medium text-destructive">
        <SafeIcon name="AlertTriangle" :size="16" />
        错误诊断
      </div>
      <div
        v-for="event in errorEvents"
        :key="event.id"
        class="rounded-md border border-destructive/20 bg-background/70 px-3 py-2"
      >
        <div class="flex items-center justify-between gap-3">
          <span class="text-xs font-medium text-foreground">{{ event.stageLabel }}</span>
          <span class="text-[10px] text-destructive">{{ event.levelLabel }}</span>
        </div>
        <p class="mt-1 text-xs text-muted-foreground leading-relaxed">{{ event.message }}</p>
        <p v-if="event.detail" class="mt-1 text-xs text-muted-foreground leading-relaxed">{{ event.detail }}</p>
      </div>
    </div>

    <div v-if="recentEvents.length" class="space-y-2">
      <p class="text-xs text-muted-foreground">最近链路</p>
      <div class="space-y-2">
        <div
          v-for="event in recentEvents"
          :key="event.id"
          class="rounded-md border border-border/60 bg-background/60 px-3 py-2"
        >
          <div class="flex items-center justify-between gap-3">
            <span class="text-xs font-medium text-foreground">{{ event.stageLabel }}</span>
            <span class="text-[10px]" :class="event.level === 'error' ? 'text-destructive' : 'text-muted-foreground'">{{ event.levelLabel }}</span>
          </div>
          <p class="mt-1 text-xs text-muted-foreground leading-relaxed">{{ event.message }}</p>
          <p v-if="event.detail" class="mt-1 text-xs text-muted-foreground leading-relaxed">{{ event.detail }}</p>
        </div>
      </div>
    </div>
  </section>
</template>
