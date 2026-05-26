
<script setup lang="ts">
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import SafeIcon from '@/components/common/SafeIcon.vue'
import type { WorkorderTimelineVO } from '@/data/WorkorderTimelineService'

const props = defineProps<{
  timeline: WorkorderTimelineVO[]
}>()

const actionLabels: Record<string, string> = {
  created: '工单创建',
  assigned: '分配责任人',
  processing: '开始处理',
  review_requested: '申请复核',
  reviewed: '完成复核',
  closed: '工单关闭'
}

const actionIcons: Record<string, string> = {
  created: 'Plus',
  assigned: 'UserPlus',
  processing: 'Play',
  review_requested: 'CheckCircle2',
  reviewed: 'CheckSquare2',
  closed: 'Archive'
}

const actionColors: Record<string, string> = {
  created: 'text-primary',
  assigned: 'text-accent',
  processing: 'text-primary',
  review_requested: 'text-[hsl(var(--warning))]',
  reviewed: 'text-[hsl(var(--success))]',
  closed: 'text-muted-foreground'
}
</script>

<template>
  <Card class="surface-base border-border/50">
    <CardHeader>
      <CardTitle class="text-lg">处理时间线</CardTitle>
      <CardDescription>工单状态变更历史</CardDescription>
    </CardHeader>
    <CardContent>
      <div v-if="timeline.length > 0" class="space-y-4">
        <div 
          v-for="(item, index) in timeline"
          :key="item.id"
          class="flex gap-4"
        >
          <!-- 时间线竖线与圆点 -->
          <div class="flex flex-col items-center">
            <div :class="['w-8 h-8 rounded-full border-2 border-border flex items-center justify-center bg-card/50', actionColors[item.action]]">
              <SafeIcon :name="actionIcons[item.action]" :size="14" />
            </div>
            <div v-if="index < timeline.length - 1" class="w-0.5 h-12 bg-border/30 mt-2" />
          </div>

          <!-- 时间线内容 -->
          <div class="flex-1 pt-1 pb-4">
            <div class="flex items-center justify-between gap-2">
              <h4 class="text-sm font-semibold text-foreground">
                {{ actionLabels[item.action] }}
              </h4>
              <span class="text-xs text-muted-foreground whitespace-nowrap">
                {{ new Date(item.createdAt).toLocaleString('zh-CN') }}
              </span>
            </div>
            <p class="text-sm text-muted-foreground mt-1">
              {{ item.note }}
            </p>
            <p v-if="item.actorUserName" class="text-xs text-muted-foreground/60 mt-2">
              操作人：{{ item.actorUserName }}
            </p>
          </div>
        </div>
      </div>
      <div v-else class="text-center py-8 text-muted-foreground">
        <SafeIcon name="Inbox" :size="32" class="mx-auto mb-2 opacity-20" />
        <p class="text-sm">暂无处理记录</p>
      </div>
    </CardContent>
  </Card>
</template>
