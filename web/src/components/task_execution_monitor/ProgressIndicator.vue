<!-- 执行进度条：展示任务当前状态和百分比，真实快照由父组件传入阶段映射进度。 -->
<script setup lang="ts">
import { computed } from 'vue'
import { Progress } from '@/components/ui/progress'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  progress: number
  status: 'queued' | 'running' | 'success' | 'failed'
}>()

// 根据任务状态生成中文状态文案。
const statusText = computed(() => {
  const map = {
    queued: '等待执行...',
    running: '执行中...',
    success: '执行完成',
    failed: '执行失败',
  }
  return map[props.status] || '未知状态'
})

// 限制进度百分比范围，避免异常数据撑破进度条。
const displayProgress = computed(() => {
  const value = Math.round(props.progress)
  if (props.status === 'queued') return 0
  if (props.status === 'success') return 100
  return Math.max(0, Math.min(100, value))
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
