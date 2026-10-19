<!-- EvidencePack 指标面板：展示智能体证据选择、置信度和复核状态。 -->

<script setup lang="ts">
import { computed } from 'vue'
import type { AgentEvidenceMetricsData } from '@/lib/api-contracts'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { cn } from '@/lib/utils'

interface MetricItem {
  label: string
  value: string
  icon: string
  tone: string
  progress?: number
}

interface Props {
  metrics?: AgentEvidenceMetricsData | null
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  metrics: null,
  loading: false,
})

// 将概率或百分制数值统一转换为 0-100 的进度值。
function toPercent(value?: number | null): number {
  if (typeof value !== 'number' || Number.isNaN(value)) return 0
  const normalized = value <= 1 ? value * 100 : value
  return Math.max(0, Math.min(100, Math.round(normalized)))
}

// 将概率或百分制数值格式化为中文界面使用的百分比。
function formatPercent(value?: number | null): string {
  return `${toPercent(value)}%`
}

// 格式化普通数值，缺失时保持占位，避免指标列宽跳动。
function formatNumber(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

// 将后端 EvidencePack 状态转换为中文状态文本。
function statusLabel(status?: string): string {
  const normalized = (status || '').toLowerCase()

  if (!normalized) return '未返回'
  if (normalized.includes('success') || normalized.includes('ready')) return '已生成'
  if (normalized.includes('review')) return '待复核'
  if (normalized.includes('failed') || normalized.includes('error')) return '异常'

  return status || '未返回'
}

// 组合面板中展示的核心指标，后续新增指标只需扩展这里。
const metricItems = computed<MetricItem[]>(() => {
  const metrics = props.metrics

  return [
    {
      label: '综合置信度',
      value: formatPercent(metrics?.confidence),
      icon: 'Gauge',
      tone: 'text-primary',
      progress: toPercent(metrics?.confidence),
    },
    {
      label: '验证器分数',
      value: formatPercent(metrics?.selectedVerifierScore),
      icon: 'SearchCheck',
      tone: 'text-[hsl(var(--success))]',
      progress: toPercent(metrics?.selectedVerifierScore),
    },
    {
      label: '候选区域',
      value: formatNumber(metrics?.candidateRegionCount),
      icon: 'ScanSearch',
      tone: 'text-foreground',
    },
    {
      label: '弃权概率',
      value: formatPercent(metrics?.abstainProbability),
      icon: 'CircleSlash',
      tone: 'text-[hsl(var(--warning))]',
      progress: toPercent(metrics?.abstainProbability),
    },
  ]
})
</script>

<template>
  <div class="surface-base card-padding space-y-3">
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h3 class="text-sm font-semibold text-foreground">EvidencePack 指标</h3>
        <p class="text-xs text-muted-foreground truncate">
          {{ loading ? '正在加载' : statusLabel(metrics?.status) }}
        </p>
      </div>
      <div
        :class="cn(
          'inline-flex items-center gap-1 rounded-[--radius] border px-2 py-1 text-[11px] whitespace-nowrap',
          metrics?.reviewRequired
            ? 'border-[hsl(var(--warning))]/30 text-[hsl(var(--warning))] bg-[hsl(var(--warning))]/10'
            : 'border-[hsl(var(--success))]/30 text-[hsl(var(--success))] bg-[hsl(var(--success))]/10',
        )"
      >
        <SafeIcon :name="metrics?.reviewRequired ? 'ClipboardCheck' : 'CheckCircle2'" :size="12" />
        <span>{{ metrics?.reviewRequired ? '待复核' : '可流转' }}</span>
      </div>
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-xs text-muted-foreground">
      <SafeIcon name="Loader2" :size="14" class="animate-spin" />
      <span>同步智能体证据指标</span>
    </div>

    <div v-else-if="metrics" class="grid grid-cols-2 gap-2">
      <div
        v-for="item in metricItems"
        :key="item.label"
        class="rounded-[--radius] border border-border/40 bg-muted/20 p-2"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="text-[11px] text-muted-foreground">{{ item.label }}</span>
          <SafeIcon :name="item.icon" :size="13" :class="item.tone" />
        </div>
        <div class="mt-1 text-base font-semibold text-foreground">{{ item.value }}</div>
        <div v-if="item.progress !== undefined" class="mt-1.5 h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            class="h-full rounded-full bg-primary transition-all"
            :style="{ width: `${item.progress}%` }"
          />
        </div>
      </div>
    </div>

    <div v-else class="flex items-center gap-2 text-xs text-muted-foreground">
      <SafeIcon name="Info" :size="14" />
      <span>暂无 EvidencePack 指标</span>
    </div>

    <div v-if="metrics?.evidenceSummary?.length" class="space-y-1">
      <div
        v-for="item in metrics.evidenceSummary.slice(0, 2)"
        :key="item"
        class="text-xs leading-relaxed text-muted-foreground rounded-[--radius] border border-border/30 bg-muted/20 px-2 py-1.5"
      >
        {{ item }}
      </div>
    </div>
  </div>
</template>
