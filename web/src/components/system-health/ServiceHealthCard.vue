
<script setup lang="ts">
import type { SystemHealthData } from '@/data/SystemHealthData'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { cn } from '@/lib/utils'

interface Props {
  service: SystemHealthData
  isSelected: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'select', serviceKey: string): void
  (e: 'retry', serviceKey: string, event: Event): void
}>()

const statusConfig = {
  healthy: {
    label: '健康',
    icon: 'CheckCircle2',
    color: 'text-[hsl(var(--success))]',
    bgColor: 'bg-[hsl(var(--success))]/10',
    borderColor: 'border-[hsl(var(--success))]/30'
  },
  degraded: {
    label: '降级',
    icon: 'AlertCircle',
    color: 'text-[hsl(var(--warning))]',
    bgColor: 'bg-[hsl(var(--warning))]/10',
    borderColor: 'border-[hsl(var(--warning))]/30'
  },
  down: {
    label: '离线',
    icon: 'XCircle',
    color: 'text-destructive',
    bgColor: 'bg-destructive/10',
    borderColor: 'border-destructive/30'
  }
}

const categoryLabel = {
  backend: '后端服务',
  model: '模型服务',
  database: '数据库'
}

const config = computed(() => statusConfig[props.service.status])
const categoryText = computed(() => categoryLabel[props.service.category])

const handleSelect = () => {
  emit('select', props.service.serviceKey)
}

const handleRetry = (event: Event) => {
  emit('retry', props.service.serviceKey, event)
}
</script>

<template>
  <div
    :class="cn(
      'surface-base card-padding cursor-pointer transition-all duration-200 space-y-3',
      isSelected && 'ring-2 ring-primary border-primary/50'
    )"
    @click="handleSelect"
  >
    <div class="flex items-start justify-between">
      <div class="space-y-1">
        <h3 class="text-item-title font-semibold">{{ service.serviceName }}</h3>
        <p class="text-caption text-muted-foreground">{{ categoryText }}</p>
      </div>
      <div 
        :class="cn(
          'p-2 rounded-lg flex items-center justify-center',
          config.bgColor
        )"
      >
        <SafeIcon :name="config.icon" :size="20" :class="config.color" />
      </div>
    </div>

    <div class="flex items-center gap-2">
      <span :class="cn('text-sm font-medium', config.color)">
        {{ config.label }}
      </span>
      <div 
        :class="cn(
          'h-2 w-2 rounded-full',
          service.status === 'healthy' && 'bg-[hsl(var(--success))] shadow-[0_0_8px_hsl(var(--success) / 0.5)]',
          service.status === 'degraded' && 'bg-[hsl(var(--warning))] shadow-[0_0_8px_hsl(var(--warning) / 0.5)]',
          service.status === 'down' && 'bg-destructive shadow-[0_0_8px_hsl(var(--destructive) / 0.5)]'
        )"
      />
    </div>

    <div class="grid grid-cols-2 gap-2 pt-2 border-t border-border/30">
      <div class="space-y-0.5">
        <p class="text-[10px] text-muted-foreground uppercase tracking-wider">延迟</p>
        <p class="text-sm font-semibold text-foreground">{{ service.latencyMs }}ms</p>
      </div>
      <div class="space-y-0.5">
        <p class="text-[10px] text-muted-foreground uppercase tracking-wider">错误数</p>
        <p :class="cn('text-sm font-semibold', service.errorCount > 0 ? 'text-destructive' : 'text-foreground')">
          {{ service.errorCount }}
        </p>
      </div>
    </div>

    <div v-if="service.status !== 'healthy'" class="pt-2 border-t border-border/30">
      <Button
        size="sm"
        variant="outline"
        class="w-full h-8 text-xs border-primary/30 hover:bg-primary/10 hover:border-primary/50 text-primary"
        @click="handleRetry"
      >
        <SafeIcon name="RotateCw" :size="12" class="mr-1" />
        一键重试
      </Button>
    </div>

    <p class="text-[10px] text-muted-foreground/60 pt-1">
      最后检查: {{ new Date(service.lastCheckedAt).toLocaleString('zh-CN') }}
    </p>
  </div>
</template>
