
<script setup lang="ts">
import { computed } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { Badge } from '@/components/ui/badge'
import type { RiskEventData } from '@/data/RiskEventData'

interface Props {
  risk: RiskEventData
  type: 'new' | 'disappeared' | 'changed'
}

const props = defineProps<Props>()

const typeConfig = computed(() => {
  const configs = {
    new: {
      icon: 'Plus',
      label: '新增',
      color: 'text-destructive',
      bgColor: 'bg-destructive/10',
      borderColor: 'border-destructive/30'
    },
    disappeared: {
      icon: 'Minus',
      label: '消失',
      color: 'text-[hsl(var(--success))]',
      bgColor: 'bg-[hsl(var(--success))]/10',
      borderColor: 'border-[hsl(var(--success))]/30'
    },
    changed: {
      icon: 'ArrowRightLeft',
      label: '变化',
      color: 'text-[hsl(var(--warning))]',
      bgColor: 'bg-[hsl(var(--warning))]/10',
      borderColor: 'border-[hsl(var(--warning))]/30'
    }
  }
  return configs[props.type]
})

const levelConfig = computed(() => {
  const configs = {
    high: { label: '高风险', color: 'text-destructive' },
    medium: { label: '中风险', color: 'text-[hsl(var(--warning))]' },
    low: { label: '低风险', color: 'text-[hsl(var(--success))]' },
    review_required: { label: '待复核', color: 'text-accent' }
  }
  return configs[props.risk.level]
})
</script>

<template>
  <div :class="cn('surface-base p-3 border-l-4 space-y-2', typeConfig.borderColor)">
    <div class="flex items-start justify-between gap-3">
      <div class="flex items-start gap-2 flex-1">
        <div :class="cn('mt-0.5 flex-shrink-0', typeConfig.color)">
          <SafeIcon :name="typeConfig.icon" :size="16" />
        </div>
        <div class="flex-1 min-w-0">
          <h4 class="text-item-title truncate">{{ risk.title }}</h4>
          <p class="text-body text-xs mt-1">{{ risk.description }}</p>
        </div>
      </div>
      <div class="flex items-center gap-2 flex-shrink-0">
        <Badge variant="outline" :class="cn('text-[10px] border-0', levelConfig.color, typeConfig.bgColor)">
          {{ levelConfig.label }}
        </Badge>
        <Badge variant="outline" :class="cn('text-[10px] border-0', typeConfig.color, typeConfig.bgColor)">
          {{ typeConfig.label }}
        </Badge>
      </div>
    </div>

    <div class="flex items-center justify-between text-xs">
      <p class="text-muted-foreground">
        风险分数: <span class="font-semibold text-foreground">{{ risk.score }}</span>
      </p>
      <p class="text-caption">
        {{ new Date(risk.triggeredAt).toLocaleString('zh-CN') }}
      </p>
    </div>

    <p class="text-caption text-muted-foreground border-t border-border/50 pt-2">
      {{ risk.evidenceSummary }}
    </p>
  </div>
</template>
