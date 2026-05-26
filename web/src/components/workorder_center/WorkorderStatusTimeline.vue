
<script setup lang="ts">
import type { WorkorderTimelineVO } from '@/data/WorkorderTimelineService'
import SafeIcon from '@/components/common/SafeIcon.vue'

const props = defineProps<{
  timeline: WorkorderTimelineVO[]
}>()

const actionIcons: Record<string, string> = {
  created: 'Plus',
  assigned: 'UserCheck',
  processing: 'Loader2',
  review_requested: 'ClipboardCheck',
  reviewed: 'CheckCircle2',
  closed: 'Archive',
}

const actionLabels: Record<string, string> = {
  created: '工单创建',
  assigned: '已分配',
  processing: '处理中',
  review_requested: '申请复核',
  reviewed: '已复核',
  closed: '已关闭',
}
</script>

<template>
  <div class="space-y-3">
    <div v-for="(item, index) in timeline" :key="item.id" class="flex gap-3">
      <!-- Timeline dot and line -->
      <div class="flex flex-col items-center">
        <div class="w-6 h-6 rounded-full bg-primary/20 border border-primary/50 flex items-center justify-center flex-shrink-0">
          <SafeIcon
            :name="actionIcons[item.action] || 'Circle'"
            :size="12"
            class="text-primary"
          />
        </div>
        <div
          v-if="index < timeline.length - 1"
          class="w-0.5 h-8 bg-gradient-to-b from-primary/50 to-primary/10 mt-1"
        />
      </div>

      <!-- Timeline content -->
      <div class="flex-1 pb-3">
        <div class="flex items-center justify-between gap-2">
          <p class="text-sm font-medium text-foreground">
            {{ actionLabels[item.action] || item.action }}
          </p>
          <span class="text-xs text-muted-foreground whitespace-nowrap">
            {{ new Date(item.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}
          </span>
        </div>
        <p class="text-xs text-muted-foreground mt-1">
          {{ item.actorUserName }} - {{ item.note }}
        </p>
      </div>
    </div>

    <div v-if="timeline.length === 0" class="text-center py-6 text-muted-foreground text-xs">
      暂无处理记录
    </div>
  </div>
</template>
