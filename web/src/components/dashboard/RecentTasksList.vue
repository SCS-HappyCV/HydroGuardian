
<script setup lang="ts">
import type { TaskData } from '@/data/TaskData'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import StatusBadge from '@/components/common/StatusBadge.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'

interface Props {
  tasks: TaskData[]
}

const props = defineProps<Props>()

const handleTaskClick = (taskId: string) => {
  window.location.href = `./task-execution-monitor.html?taskId=${taskId}`
}

const handleViewMore = () => {
  window.location.href = './history.html'
}

const formatTime = (dateStr: string) => {
  try {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = Math.floor((now.getTime() - date.getTime()) / 1000)
    
    if (diff < 60) return `${Math.max(0, diff)}秒前`
    if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
    if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
    if (diff < 2592000) return `${Math.floor(diff / 86400)}天前`
    if (diff < 31536000) return `${Math.floor(diff / 2592000)}个月前`
    return `${Math.floor(diff / 31536000)}年前`
  } catch {
    return dateStr
  }
}
</script>

<template>
  <div class="surface-base card-padding space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-section-title">最近执行任务</h3>
      <Button 
        variant="ghost" 
        size="sm"
        class="text-primary hover:bg-primary/10"
        @click="handleViewMore"
      >
        更多历史
        <SafeIcon name="ChevronRight" :size="14" class="ml-1" />
      </Button>
    </div>

    <div class="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow class="hover:bg-transparent border-b border-border/50">
            <TableHead class="whitespace-nowrap w-32 h-10 px-4 text-xs font-semibold uppercase text-muted-foreground">任务名称</TableHead>
            <TableHead class="whitespace-nowrap w-24 h-10 px-4 text-xs font-semibold uppercase text-muted-foreground">状态</TableHead>
            <TableHead class="whitespace-nowrap w-20 h-10 px-4 text-xs font-semibold uppercase text-muted-foreground">优先级</TableHead>
            <TableHead class="whitespace-nowrap w-28 h-10 px-4 text-xs font-semibold uppercase text-muted-foreground">执行时间</TableHead>
            <TableHead class="whitespace-nowrap w-16 h-10 px-4 text-xs font-semibold uppercase text-muted-foreground">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow 
            v-for="task in tasks" 
            :key="task.id"
            class="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors cursor-pointer"
            @click="handleTaskClick(task.id)"
          >
            <TableCell class="px-4 py-3 text-sm text-card-foreground truncate">
              {{ task.name }}
            </TableCell>
            <TableCell class="px-4 py-3">
              <StatusBadge :status="task.status" size="sm" />
            </TableCell>
            <TableCell class="px-4 py-3 text-sm text-muted-foreground">
              <span :class="cn(
                'inline-block px-2 py-1 rounded text-[10px] font-medium',
                task.priority === 'high' && 'bg-destructive/20 text-destructive',
                task.priority === 'medium' && 'bg-warning/20 text-warning',
                task.priority === 'low' && 'bg-success/20 text-success'
              )">
                {{ task.priority === 'high' ? '高' : task.priority === 'medium' ? '中' : '低' }}
              </span>
            </TableCell>
            <TableCell class="px-4 py-3 text-sm text-muted-foreground whitespace-nowrap">
              {{ formatTime(task.createdAt) }}
            </TableCell>
            <TableCell class="px-4 py-3 text-center">
              <Button 
                variant="ghost" 
                size="icon" 
                class="h-6 w-6 text-muted-foreground hover:text-primary"
                @click.stop="handleTaskClick(task.id)"
              >
                <SafeIcon name="ChevronRight" :size="14" />
              </Button>
            </TableCell>
          </TableRow>
          
          <TableRow v-if="tasks.length === 0">
            <TableCell colspan="5" class="h-20 text-center">
              <div class="flex flex-col items-center justify-center text-muted-foreground">
                <SafeIcon name="Inbox" :size="24" class="mb-2 opacity-20" />
                <span class="text-sm">暂无任务记录</span>
              </div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
</template>
