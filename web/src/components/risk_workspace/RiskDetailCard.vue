
<script setup lang="ts">
import type { RiskEventData } from '@/data/RiskEventData'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import StatusBadge from '@/components/common/StatusBadge.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'

interface Props {
  risk: RiskEventData
}

const emit = defineEmits<{
  (e: 'create-workorder'): void
  (e: 'mark-review'): void
}>()

const formatDate = (dateStr?: string) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <div class="surface-base card-padding flex flex-col gap-4 max-h-[500px] overflow-y-auto">
    <!-- Header -->
    <div class="space-y-2">
      <div class="flex items-start justify-between gap-2">
        <h3 class="text-base font-semibold text-foreground flex-1 leading-tight">
          {{ risk?.title }}
        </h3>
        <StatusBadge :status="risk?.level" size="sm" />
      </div>
      <p class="text-xs text-muted-foreground leading-relaxed">
        {{ risk?.description }}
      </p>
    </div>

    <Separator class="opacity-30" />

    <!-- Risk details -->
    <div class="space-y-3 text-xs">
      <div class="flex items-center justify-between">
        <span class="text-muted-foreground">风险分数</span>
        <span class="font-bold text-foreground">{{ risk?.score }}/100</span>
      </div>

      <div class="flex items-center justify-between">
        <span class="text-muted-foreground">触发时间</span>
        <span class="text-foreground">{{ formatDate(risk?.triggeredAt) }}</span>
      </div>

      <div class="flex items-center justify-between">
        <span class="text-muted-foreground">最后更新</span>
        <span class="text-foreground">{{ formatDate(risk?.updatedAt) }}</span>
      </div>

      <div class="flex items-center justify-between">
        <span class="text-muted-foreground">当前状态</span>
        <StatusBadge :status="risk?.status === 'linked' ? 'doing' : risk?.status === 'closed' ? 'closed' : 'review'" size="sm" />
      </div>
    </div>

    <Separator class="opacity-30" />

    <!-- Evidence summary -->
    <div class="space-y-2">
      <h4 class="text-xs font-semibold text-foreground uppercase tracking-wider">
        证据摘要
      </h4>
      <p class="text-xs text-muted-foreground leading-relaxed bg-muted/20 p-2 rounded border border-border/30">
        {{ risk?.evidenceSummary }}
      </p>
    </div>

    <!-- Actions -->
    <div class="flex flex-col gap-2 pt-2">
      <Button
        variant="default"
        size="sm"
        class="w-full gap-2"
        @click="emit('create-workorder')"
      >
        <SafeIcon name="Plus" :size="14" />
        一键创建工单
      </Button>

      <Button
        v-if="risk?.status !== 'review_required'"
        variant="outline"
        size="sm"
        class="w-full gap-2"
        @click="emit('mark-review')"
      >
        <SafeIcon name="Flag" :size="14" />
        标记待复核
      </Button>

      <Button
        v-else
        variant="outline"
        size="sm"
        class="w-full gap-2 text-accent border-accent/30"
        disabled
      >
        <SafeIcon name="CheckCircle2" :size="14" />
        已标记待复核
      </Button>
    </div>
  </div>
</template>
