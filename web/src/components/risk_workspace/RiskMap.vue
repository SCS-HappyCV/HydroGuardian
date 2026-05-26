
<script setup lang="ts">
import { computed } from 'vue'
import type { RiskEventData } from '@/data/RiskEventData'
import type { ZoneData } from '@/data/ZoneData'
import SafeIcon from '@/components/common/SafeIcon.vue'

interface Props {
  risks: RiskEventData[]
  zones: ZoneData[]
  selectedRiskId: string | null
  zoneId: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'risk-click', riskId: string): void
}>()

const risksByLevel = computed(() => {
  return {
    high: props.risks.filter(r => r.level === 'high'),
    medium: props.risks.filter(r => r.level === 'medium'),
    low: props.risks.filter(r => r.level === 'low'),
    review_required: props.risks.filter(r => r.level === 'review_required'),
  }
})

const handleRiskClick = (riskId: string) => {
  emit('risk-click', riskId)
}
</script>

<template>
  <div class="w-full h-full flex flex-col bg-gradient-to-br from-muted/30 to-background relative overflow-hidden">
    <!-- Map placeholder with risk visualization -->
    <div class="flex-1 relative flex items-center justify-center">
      <!-- Background grid pattern -->
      <div class="absolute inset-0 opacity-5">
        <svg class="w-full h-full" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="currentColor" stroke-width="0.5" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
      </div>

      <!-- Risk points visualization -->
      <div class="absolute inset-0 flex items-center justify-center">
        <div class="relative w-full h-full">
          <!-- High risk points (red) -->
          <div
            v-for="risk in risksByLevel.high"
            :key="`high-${risk?.id}`"
            class="absolute w-3 h-3 rounded-full bg-destructive cursor-pointer transform -translate-x-1/2 -translate-y-1/2 hover:scale-150 transition-transform shadow-lg shadow-destructive/50"
            :style="{
              left: `${20 + ((risk?.score || 0) % 60)}%`,
              top: `${30 + ((risk?.score || 0) % 40)}%`,
            }"
            :class="selectedRiskId === risk?.id && 'ring-2 ring-destructive ring-offset-2 ring-offset-background scale-150'"
            @click="handleRiskClick(risk?.id || '')"
            :title="`${risk?.title} (${risk?.score}分)`"
          />

          <!-- Medium risk points (orange) -->
          <div
            v-for="risk in risksByLevel.medium"
            :key="`medium-${risk?.id}`"
            class="absolute w-2.5 h-2.5 rounded-full bg-[hsl(var(--warning))] cursor-pointer transform -translate-x-1/2 -translate-y-1/2 hover:scale-150 transition-transform shadow-lg shadow-[hsl(var(--warning) / 0.5)]"
            :style="{
              left: `${35 + ((risk?.score || 0) % 50)}%`,
              top: `${45 + ((risk?.score || 0) % 35)}%`,
            }"
            :class="selectedRiskId === risk?.id && 'ring-2 ring-[hsl(var(--warning))] ring-offset-2 ring-offset-background scale-150'"
            @click="handleRiskClick(risk?.id || '')"
            :title="`${risk?.title} (${risk?.score}分)`"
          />

          <!-- Low risk points (green) -->
          <div
            v-for="risk in risksByLevel.low"
            :key="`low-${risk?.id}`"
            class="absolute w-2 h-2 rounded-full bg-[hsl(var(--success))] cursor-pointer transform -translate-x-1/2 -translate-y-1/2 hover:scale-150 transition-transform shadow-lg shadow-[hsl(var(--success) / 0.5)]"
            :style="{
              left: `${50 + ((risk?.score || 0) % 40)}%`,
              top: `${60 + ((risk?.score || 0) % 30)}%`,
            }"
            :class="selectedRiskId === risk?.id && 'ring-2 ring-[hsl(var(--success))] ring-offset-2 ring-offset-background scale-150'"
            @click="handleRiskClick(risk?.id || '')"
            :title="`${risk?.title} (${risk?.score}分)`"
          />

          <!-- Review required points (cyan) -->
          <div
            v-for="risk in risksByLevel.review_required"
            :key="`review-${risk?.id}`"
            class="absolute w-2.5 h-2.5 rounded-full bg-accent cursor-pointer transform -translate-x-1/2 -translate-y-1/2 hover:scale-150 transition-transform shadow-lg shadow-accent/50 animate-pulse"
            :style="{
              left: `${65 + ((risk?.score || 0) % 30)}%`,
              top: `${50 + ((risk?.score || 0) % 35)}%`,
            }"
            :class="selectedRiskId === risk?.id && 'ring-2 ring-accent ring-offset-2 ring-offset-background scale-150'"
            @click="handleRiskClick(risk?.id || '')"
            :title="`${risk?.title} (待复核)`"
          />
        </div>
      </div>

      <!-- Legend -->
      <div class="absolute bottom-4 left-4 surface-base card-padding space-y-2 text-xs">
        <div class="flex items-center gap-2">
          <div class="w-2.5 h-2.5 rounded-full bg-destructive" />
          <span class="text-foreground">高风险</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-2.5 h-2.5 rounded-full bg-[hsl(var(--warning))]" />
          <span class="text-foreground">中风险</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-2.5 h-2.5 rounded-full bg-[hsl(var(--success))]" />
          <span class="text-foreground">低风险</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-2.5 h-2.5 rounded-full bg-accent animate-pulse" />
          <span class="text-foreground">待复核</span>
        </div>
      </div>

      <!-- Info text -->
      <div v-if="risks.length === 0" class="absolute inset-0 flex items-center justify-center">
        <div class="text-center text-muted-foreground">
          <SafeIcon name="MapPin" :size="48" class="mx-auto mb-2 opacity-20" />
          <p class="text-sm">未发现高风险，建议查看待复核</p>
        </div>
      </div>
    </div>

    <!-- Map controls -->
    <div class="flex-shrink-0 border-t border-border/50 bg-background/50 backdrop-blur-sm p-2 flex items-center justify-between">
      <div class="text-xs text-muted-foreground">
        显示 {{ risks.length }} 个风险点
      </div>
      <div class="flex items-center gap-1">
        <button class="p-1.5 hover:bg-muted/50 rounded transition-colors" title="放大">
          <SafeIcon name="ZoomIn" :size="16" />
        </button>
        <button class="p-1.5 hover:bg-muted/50 rounded transition-colors" title="缩小">
          <SafeIcon name="ZoomOut" :size="16" />
        </button>
        <button class="p-1.5 hover:bg-muted/50 rounded transition-colors" title="重置视图">
          <SafeIcon name="Maximize2" :size="16" />
        </button>
      </div>
    </div>
  </div>
</template>
