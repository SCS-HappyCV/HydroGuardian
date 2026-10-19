<!-- 前后影像对比面板：展示灾前/灾后影像、变化指标和可选变化掩膜。 -->

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AgentChangeComparisonData } from '@/lib/api-contracts'
import { resolveFileDownloadUrl } from '@/lib/file-asset-url'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { cn } from '@/lib/utils'

interface Props {
  comparison?: AgentChangeComparisonData | null
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  comparison: null,
  loading: false,
})

const splitPercent = ref(50)

const preImageUrl = computed(() => resolveFileDownloadUrl(props.comparison?.preImage?.downloadUrl))
const postImageUrl = computed(() => resolveFileDownloadUrl(props.comparison?.postImage?.downloadUrl))
const maskImageUrl = computed(() => resolveFileDownloadUrl(props.comparison?.changeMask?.downloadUrl))
const hasImagePair = computed(() => Boolean(preImageUrl.value && postImageUrl.value))
const hasMask = computed(() => Boolean(maskImageUrl.value))

// 将变化概率或百分制分数转换为 0-100 展示值。
function toPercent(value?: number | null): number {
  if (typeof value !== 'number' || Number.isNaN(value)) return 0
  const normalized = value <= 1 ? value * 100 : value
  return Math.max(0, Math.min(100, Math.round(normalized)))
}

// 格式化变化分数，缺失时保持短占位。
function formatChangeScore(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return `${toPercent(value)}%`
}

// 将后端变化类型转换为中文短标签。
function changeTypeLabel(changeType?: string | null): string {
  const normalized = (changeType || '').trim().toLowerCase()

  if (!normalized) return '未返回'
  if (normalized.includes('increase') || normalized.includes('new')) return '新增/扩大'
  if (normalized.includes('decrease') || normalized.includes('recover')) return '减少/恢复'
  if (normalized.includes('stable') || normalized.includes('none')) return '基本稳定'

  return changeType || '未返回'
}

// 将后端状态转换为中文，用于面板副标题。
function statusLabel(status?: string | null): string {
  const normalized = (status || '').trim().toLowerCase()

  if (!normalized) return '未返回'
  if (normalized.includes('success') || normalized.includes('ready')) return '已生成'
  if (normalized.includes('skip')) return '未启用'
  if (normalized.includes('failed') || normalized.includes('error')) return '异常'

  return status || '未返回'
}

// 对齐状态直接影响前后影像可比性，需要单独中文化。
function alignmentLabel(status?: string | null): string {
  const normalized = (status || '').trim().toLowerCase()

  if (!normalized) return '未返回'
  if (normalized.includes('aligned') || normalized.includes('success')) return '已对齐'
  if (normalized.includes('rough')) return '粗对齐'
  if (normalized.includes('failed') || normalized.includes('error')) return '对齐异常'

  return status || '未返回'
}

// 更新滑杆位置，并限制在可视范围内。
function handleSplitInput(event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  splitPercent.value = Math.max(5, Math.min(95, value))
}
</script>

<template>
  <div class="surface-base card-padding space-y-3">
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h3 class="text-sm font-semibold text-foreground">前后影像对比</h3>
        <p class="text-xs text-muted-foreground truncate">
          {{ loading ? '正在加载' : statusLabel(comparison?.status) }}
        </p>
      </div>
      <div
        :class="cn(
          'inline-flex items-center gap-1 rounded-[--radius] border px-2 py-1 text-[11px] whitespace-nowrap',
          !comparison
            ? 'border-border/40 text-muted-foreground bg-muted/20'
            : comparison.reviewRequired
            ? 'border-[hsl(var(--warning))]/30 text-[hsl(var(--warning))] bg-[hsl(var(--warning))]/10'
            : 'border-[hsl(var(--success))]/30 text-[hsl(var(--success))] bg-[hsl(var(--success))]/10',
        )"
      >
        <SafeIcon :name="!comparison ? 'Info' : comparison.reviewRequired ? 'ClipboardCheck' : 'CheckCircle2'" :size="12" />
        <span>{{ !comparison ? '未返回' : comparison.reviewRequired ? '待复核' : '可流转' }}</span>
      </div>
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-xs text-muted-foreground">
      <SafeIcon name="Loader2" :size="14" class="animate-spin" />
      <span>同步前后影像</span>
    </div>

    <div v-else class="space-y-3">
      <div v-if="hasImagePair" class="space-y-2">
        <div class="relative aspect-[16/9] overflow-hidden rounded-[--radius] border border-border/40 bg-muted/20">
          <img
            :src="preImageUrl"
            alt="前影像"
            class="absolute inset-0 h-full w-full object-cover"
            loading="lazy"
          >
          <div class="absolute inset-y-0 right-0 overflow-hidden" :style="{ width: `${100 - splitPercent}%` }">
            <img
              :src="postImageUrl"
              alt="后影像"
              class="absolute inset-y-0 right-0 h-full object-cover"
              :style="{ width: `${10000 / Math.max(1, 100 - splitPercent)}%` }"
              loading="lazy"
            >
          </div>
          <div class="absolute inset-y-0 w-px bg-primary shadow-[0_0_12px_hsl(var(--primary))]" :style="{ left: `${splitPercent}%` }" />
          <div class="absolute left-2 top-2 rounded-[--radius] bg-background/85 px-2 py-1 text-[11px] text-foreground backdrop-blur">
            前影像
          </div>
          <div class="absolute right-2 top-2 rounded-[--radius] bg-background/85 px-2 py-1 text-[11px] text-foreground backdrop-blur">
            后影像
          </div>
          <img
            v-if="hasMask"
            :src="maskImageUrl"
            alt="变化掩膜"
            class="absolute inset-0 h-full w-full object-cover mix-blend-screen opacity-45"
            loading="lazy"
          >
        </div>

        <div class="flex items-center gap-2">
          <SafeIcon name="ImageMinus" :size="14" class="text-muted-foreground" />
          <input
            :value="splitPercent"
            type="range"
            min="5"
            max="95"
            step="1"
            class="h-1.5 flex-1 cursor-pointer accent-primary"
            aria-label="前后影像分割位置"
            @input="handleSplitInput"
          >
          <SafeIcon name="ImagePlus" :size="14" class="text-muted-foreground" />
        </div>
      </div>

      <div v-else class="flex items-center gap-2 rounded-[--radius] border border-border/30 bg-muted/20 px-2 py-2 text-xs text-muted-foreground">
        <SafeIcon name="Images" :size="14" />
        <span>暂无可对比影像</span>
      </div>

      <div class="grid grid-cols-3 gap-2 text-xs">
        <div class="rounded-[--radius] border border-border/40 bg-muted/20 p-2">
          <div class="text-[11px] text-muted-foreground">变化类型</div>
          <div class="mt-1 truncate font-medium text-foreground">{{ changeTypeLabel(comparison?.changeType) }}</div>
        </div>
        <div class="rounded-[--radius] border border-border/40 bg-muted/20 p-2">
          <div class="text-[11px] text-muted-foreground">变化分数</div>
          <div class="mt-1 font-medium text-foreground">{{ formatChangeScore(comparison?.changeScore) }}</div>
        </div>
        <div class="rounded-[--radius] border border-border/40 bg-muted/20 p-2">
          <div class="text-[11px] text-muted-foreground">对齐状态</div>
          <div class="mt-1 truncate font-medium text-foreground">{{ alignmentLabel(comparison?.alignmentStatus) }}</div>
        </div>
      </div>

      <div
        v-if="comparison?.changeSummary"
        class="rounded-[--radius] border border-border/30 bg-muted/20 px-2 py-1.5 text-xs leading-relaxed text-muted-foreground"
      >
        {{ comparison.changeSummary }}
      </div>
    </div>
  </div>
</template>
