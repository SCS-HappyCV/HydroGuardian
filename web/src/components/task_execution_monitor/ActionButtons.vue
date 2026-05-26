
<script setup lang="ts">
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  status: 'queued' | 'running' | 'success' | 'failed'
  isRunning: boolean
  isSuccess: boolean
  isFailed: boolean
  isQueued: boolean
}>()

const emit = defineEmits<{
  (e: 'stop'): void
  (e: 'retry'): void
  (e: 'modify-params'): void
  (e: 'view-results'): void
  (e: 'view-system-health'): void
}>()
</script>

<template>
  <div class="surface-base card-padding flex flex-wrap items-center gap-3">
    <template v-if="isRunning">
      <Button 
        variant="destructive"
        class="gap-2"
        @click="emit('stop')"
      >
        <SafeIcon name="Square" :size="16" />
        停止任务
      </Button>
      <p class="text-xs text-muted-foreground">
        任务正在执行中，点击停止按钮可中断任务。
      </p>
    </template>

    <template v-else-if="isSuccess">
      <Button 
        class="gap-2 bg-[hsl(var(--success))] hover:bg-[hsl(var(--success))]/90 text-white"
        @click="emit('view-results')"
      >
        <SafeIcon name="Eye" :size="16" />
        查看风险结果
      </Button>
      <p class="text-xs text-muted-foreground">
        任务执行成功，可查看生成的风险分析结果。
      </p>
    </template>

    <template v-else-if="isFailed">
      <Button 
        class="gap-2"
        @click="emit('retry')"
      >
        <SafeIcon name="RotateCcw" :size="16" />
        重新执行
      </Button>
      <Button 
        variant="outline"
        class="gap-2"
        @click="emit('modify-params')"
      >
        <SafeIcon name="Edit2" :size="16" />
        修改参数
      </Button>
      <Button 
        variant="ghost"
        class="gap-2 text-destructive hover:text-destructive hover:bg-destructive/10"
        @click="emit('view-system-health')"
      >
        <SafeIcon name="AlertTriangle" :size="16" />
        查看系统状态
      </Button>
      <p class="text-xs text-muted-foreground">
        任务执行失败，可重试或检查系统健康状态。
      </p>
    </template>

    <template v-else-if="isQueued">
      <Button 
        variant="outline"
        class="gap-2"
        @click="emit('modify-params')"
      >
        <SafeIcon name="Edit2" :size="16" />
        修改参数
      </Button>
      <p class="text-xs text-muted-foreground">
        任务已加入队列，等待执行资源释放。
      </p>
    </template>
  </div>
</template>
