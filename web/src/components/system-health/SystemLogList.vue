
<script setup lang="ts">
import type { SystemLogData } from '@/data/SystemLogData'
import * as SystemHealthService from '@/data/SystemHealthService'
import { Button } from '@/components/ui/button'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { toast } from 'vue-sonner'
import { cn } from '@/lib/utils'

interface Props {
  logs: SystemLogData[]
  selectedServiceKey: string | null
}

const props = defineProps<Props>()

const levelConfig = {
  info: {
    label: '信息',
    icon: 'Info',
    color: 'text-primary',
    bgColor: 'bg-primary/10',
    borderColor: 'border-l-primary/50'
  },
  warn: {
    label: '警告',
    icon: 'AlertCircle',
    color: 'text-[hsl(var(--warning))]',
    bgColor: 'bg-[hsl(var(--warning))]/10',
    borderColor: 'border-l-[hsl(var(--warning))]'
  },
  error: {
    label: '错误',
    icon: 'AlertTriangle',
    color: 'text-destructive',
    bgColor: 'bg-destructive/10',
    borderColor: 'border-l-destructive'
  }
}

const getServiceName = (serviceHealthId: string) => {
  const service = SystemHealthService.getById(serviceHealthId)
  return service?.serviceName || '未知服务'
}

const handleLogClick = (log: SystemLogData) => {
  toast.info(`错误详情: ${log.message}`)
}

const sortedLogs = computed(() => {
  return [...props.logs].sort((a, b) => 
    new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
  )
})
</script>

<template>
  <div class="space-y-2">
    <div v-if="sortedLogs.length === 0" class="text-center py-12 text-muted-foreground">
      <SafeIcon name="Inbox" :size="32" class="mx-auto mb-2 opacity-20" />
      <p>暂无日志记录</p>
    </div>

    <div v-for="log in sortedLogs" :key="log.id" class="space-y-2">
      <div
        :class="cn(
          'surface-base card-padding cursor-pointer transition-all hover:bg-card/50 border-l-2',
          levelConfig[log.level].borderColor
        )"
        @click="handleLogClick(log)"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="flex-1 min-w-0 space-y-1">
            <div class="flex items-center gap-2">
              <div :class="cn('p-1.5 rounded-md', levelConfig[log.level].bgColor)">
                <SafeIcon 
                  :name="levelConfig[log.level].icon" 
                  :size="14" 
                  :class="levelConfig[log.level].color"
                />
              </div>
              <span :class="cn('text-xs font-semibold', levelConfig[log.level].color)">
                {{ levelConfig[log.level].label }}
              </span>
              <span class="text-xs text-muted-foreground">
                {{ getServiceName(log.serviceHealthId) }}
              </span>
              <span v-if="log.taskId" class="text-xs text-muted-foreground/60">
                (任务: {{ log.taskId }})
              </span>
            </div>
            
            <p class="text-sm text-foreground leading-relaxed break-words">
              {{ log.message }}
            </p>
            
            <p class="text-[10px] text-muted-foreground/60">
              {{ new Date(log.createdAt).toLocaleString('zh-CN') }}
            </p>
          </div>

          <Button
            variant="ghost"
            size="icon"
            class="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
            @click.stop="handleLogClick(log)"
          >
            <SafeIcon name="ChevronRight" :size="16" />
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
