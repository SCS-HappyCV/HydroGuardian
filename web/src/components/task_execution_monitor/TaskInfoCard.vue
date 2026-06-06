<!-- 任务信息卡：展示任务基础信息、优先级、时间和描述。 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { TaskData } from '@/data/TaskData'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  task: TaskData
}>()

// 格式化任务时间，缺失值统一展示为短横线。
function formatTime(dateStr: string | undefined): string {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// 计算任务执行耗时，未完成时不展示耗时。
const duration = computed(() => {
  if (!props.task.startedAt || !props.task.finishedAt) return '-'
  const start = new Date(props.task.startedAt).getTime()
  const end = new Date(props.task.finishedAt).getTime()
  const seconds = Math.max(0, Math.floor((end - start) / 1000))
  return `${seconds} 秒`
})

// 根据优先级生成徽标颜色。
const priorityColor = computed(() => {
  switch (props.task.priority) {
    case 'high':
      return 'destructive'
    case 'medium':
      return 'warning'
    default:
      return 'secondary'
  }
})

// 根据优先级生成中文文案。
const priorityLabel = computed(() => {
  const map = { high: '高', medium: '中', low: '低' }
  return map[props.task.priority] || '未知'
})
</script>

<template>
  <Card class="surface-base border-border">
    <CardHeader class="pb-3">
      <div class="flex items-start justify-between gap-4">
        <div>
          <CardTitle class="text-xl">{{ task.name }}</CardTitle>
          <CardDescription class="mt-1 text-xs">
            任务 ID：{{ task.id }}
          </CardDescription>
        </div>
        <div class="flex items-center gap-2">
          <StatusBadge :status="task.status" size="md" />
          <Badge
            :class="cn(
              'px-2 py-1 text-xs font-medium border',
              priorityColor === 'destructive' && 'bg-destructive/20 text-destructive border-destructive/30',
              priorityColor === 'warning' && 'bg-[hsl(var(--warning))]/20 text-[hsl(var(--warning))] border-[hsl(var(--warning))]/30',
              priorityColor === 'secondary' && 'bg-secondary/20 text-secondary-foreground border-secondary/30'
            )"
          >
            {{ priorityLabel }}优先级
          </Badge>
        </div>
      </div>
    </CardHeader>

    <CardContent class="space-y-4">
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="space-y-1">
          <p class="text-xs text-muted-foreground">创建时间</p>
          <p class="text-sm font-medium">{{ formatTime(task.createdAt) }}</p>
        </div>
        <div class="space-y-1">
          <p class="text-xs text-muted-foreground">开始时间</p>
          <p class="text-sm font-medium">{{ formatTime(task.startedAt) }}</p>
        </div>
        <div class="space-y-1">
          <p class="text-xs text-muted-foreground">完成时间</p>
          <p class="text-sm font-medium">{{ formatTime(task.finishedAt) }}</p>
        </div>
        <div class="space-y-1">
          <p class="text-xs text-muted-foreground">执行耗时</p>
          <p class="text-sm font-medium">{{ duration }}</p>
        </div>
      </div>

      <div class="pt-2 border-t border-border/50">
        <p class="text-xs text-muted-foreground mb-2">任务描述</p>
        <p class="text-sm text-card-foreground leading-relaxed break-words">
          {{ task.inputText }}
        </p>
      </div>
    </CardContent>
  </Card>
</template>
