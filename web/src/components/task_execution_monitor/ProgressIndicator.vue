
<script setup lang="ts">
import { computed } from 'vue'
import { Progress } from '@/components/ui/progress'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  progress: number
  status: 'queued' | 'running' | 'success' | 'failed'
}>()

const statusText = computed(() => {
  const map = {
    queued: '等待执行...',
    running: '执行中...',
    success: '执行完成',
    failed: '执行失败'
  }
  return map[props.status] || '未知状态'
})

const statusColor = computed(() => {
  switch (props.status) {
    case 'success':
      return 'bg-[hsl(var(--success))]'
    case 'failed':
      return 'bg-destructive'
    case 'running':
      return 'bg-primary'
    default:
      return 'bg-muted'
  }
})

const displayProgress = computed(() => {
  if (props.status === 'queued') return 0
  if (props.status === 'success') return 100
  if (props.status === 'failed') return props.progress
  return props.progress
})
</script>

<template>
  <div class="surface-base card-padding space-y-3">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <SafeIcon 
          :name="status === 'running' ? 'Loader2' : status === 'success' ? 'CheckCircle2' : status === 'failed' ? 'XCircle' : 'Clock'"
          :size="18"
          :class="cn(
            status === 'running' && 'animate-spin text-primary',
            status === 'success' && 'text-[hsl(var(--success))]',
            status === 'failed' && 'text-destructive',
            status === 'queued' && 'text-muted-foreground'
          )"
        />
        <span class="text-sm font-medium">{{ statusText }}</span>
      </div>
      <span class="text-sm font-semibold text-primary">{{ displayProgress }}%</span>
    </div>

    <Progress 
      :value="displayProgress" 
      class="h-2"
      :class="cn(
        '[&>div]:transition-all [&>div]:duration-500',
        status === 'running' && '[&>div]:animate-pulse'
      )"
    />

    <div v-if="status === 'running'" class="text-xs text-muted-foreground">
      任务正在后台执行，请勿关闭此页面。
    </div>
  </div>
</template>
