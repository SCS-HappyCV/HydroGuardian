<script setup lang="ts">
import type { RiskEventData } from '@/data/RiskEventData'
import StatusBadge from '@/components/common/StatusBadge.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'

interface Props {
  risks: RiskEventData[]
  selectedRiskId: string | null
  hoveredRiskId?: string | null
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'row-click', risk: RiskEventData): void
  (e: 'row-hover', riskId: string | null): void
}>()

function levelAccent(level: RiskEventData['level']): string {
  if (level === 'high') return 'bg-[#ff5d5d]'
  if (level === 'medium') return 'bg-[#f5b942]'
  if (level === 'low') return 'bg-[#39c98a]'
  return 'bg-[#8b7cff]'
}

function scoreTone(level: RiskEventData['level']): string {
  if (level === 'high') return 'text-[#ff837c]'
  if (level === 'medium') return 'text-[#ffd06b]'
  if (level === 'low') return 'text-[#63e3af]'
  return 'text-[#b8adff]'
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden">
    <div class="flex items-center justify-between border-b border-border/50 px-3 py-3">
      <div>
        <h2 class="text-sm font-semibold text-foreground">候选风险队列</h2>
        <p class="mt-0.5 text-[11px] text-muted-foreground">按优先级联动证据画布</p>
      </div>
      <span class="rounded-full border border-primary/20 bg-primary/10 px-2 py-1 text-[11px] font-semibold text-primary">
        {{ risks.length }} 个候选
      </span>
    </div>

    <div class="flex-1 space-y-2 overflow-y-auto p-2">
      <button
        v-for="(risk, index) in risks"
        :key="risk.id"
        type="button"
        class="group relative w-full overflow-hidden rounded-xl border p-3 text-left transition-all"
        :class="selectedRiskId === risk.id
          ? 'border-cyan-400/50 bg-cyan-400/[0.08] shadow-[0_0_24px_rgba(45,212,191,.08)]'
          : hoveredRiskId === risk.id ? 'border-cyan-300/25 bg-cyan-300/[0.035]' : 'border-border/45 bg-card/35 hover:border-border hover:bg-muted/25'"
        @click="emit('row-click', risk)"
        @pointerenter="emit('row-hover', risk.id)"
        @pointerleave="emit('row-hover', null)"
        @focus="emit('row-hover', risk.id)"
        @blur="emit('row-hover', null)"
      >
        <i class="absolute inset-y-0 left-0 w-1" :class="levelAccent(risk.level)" />

        <div class="flex items-start justify-between gap-3 pl-1">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="text-[10px] font-semibold tracking-widest text-muted-foreground">R{{ String(index + 1).padStart(2, '0') }}</span>
              <StatusBadge :status="risk.level" size="sm" />
            </div>
            <h3 class="mt-2 line-clamp-2 text-xs font-semibold leading-relaxed text-foreground">
              {{ risk.title }}
            </h3>
          </div>
          <div class="shrink-0 text-right">
            <div class="text-[10px] text-muted-foreground">风险分</div>
            <div class="mt-0.5 text-xl font-bold leading-none" :class="scoreTone(risk.level)">{{ risk.score }}</div>
          </div>
        </div>

        <div class="mt-3 flex items-center justify-between gap-2 border-t border-border/30 pt-2 text-[10px] text-muted-foreground">
          <span class="flex min-w-0 items-center gap-1 truncate">
            <SafeIcon name="Layers3" :size="11" />
            {{ risk.level === 'review_required' ? '证据冲突 · 需复核' : '多模态证据已聚合' }}
          </span>
          <SafeIcon
            name="ChevronRight"
            :size="13"
            class="shrink-0 transition-transform group-hover:translate-x-0.5"
            :class="selectedRiskId === risk.id ? 'text-cyan-300' : ''"
          />
        </div>
      </button>

      <div v-if="risks.length === 0" class="flex h-40 flex-col items-center justify-center text-muted-foreground">
        <SafeIcon name="Inbox" :size="28" class="mb-2 opacity-30" />
        <span class="text-xs">当前条件下暂无风险</span>
      </div>
    </div>
  </div>
</template>
