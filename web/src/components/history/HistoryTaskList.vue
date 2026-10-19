
<script setup lang="ts">
import { computed } from 'vue'
import type { TaskData } from '@/data/TaskData'
import * as TaskResultService from '@/data/TaskResultService'
import * as ZoneService from '@/data/ZoneService'
import * as TaskTemplateService from '@/data/TaskTemplateService'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import StatusBadge from '@/components/common/StatusBadge.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import { cn } from '@/lib/utils'

const props = defineProps<{
  tasks: TaskData[]
  selectedTaskIds: Set<string>
  isClient: boolean
}>()

const emit = defineEmits<{
  (e: 'task-select', taskId: string, selected: boolean): void
  (e: 'task-row-click', taskId: string): void
}>()

const getTaskResult = (taskId: string) => {
  return TaskResultService.getById(TaskResultService.taskResultDataList.find(r => r.taskId === taskId)?.id || '')
}

const getZoneName = (zoneId: string) => {
  return ZoneService.getById(zoneId)?.name || '-'
}

const getTemplateName = (templateId: string) => {
  return TaskTemplateService.getById(templateId)?.name || '-'
}

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const handleCheckboxChange = (taskId: string, checked: boolean) => {
  emit('task-select', taskId, checked)
}

const handleRowClick = (taskId: string, e: MouseEvent) => {
  if ((e.target as HTMLElement).closest('input[type="checkbox"]')) {
    return
  }
  emit('task-row-click', taskId)
}

const allSelected = computed(() => {
  return props.tasks.length > 0 && props.tasks.every(t => props.selectedTaskIds.has(t.id))
})

const handleSelectAll = (checked: boolean) => {
  props.tasks.forEach(task => {
    emit('task-select', task.id, checked)
  })
}
</script>

<template>
  <div v-if="tasks.length === 0" class="surface-base card-padding">
    <EmptyState 
      icon="History"
      title="暂无历史任务"
      description="还没有执行过任何任务，请前往任务工作坊创建新任务"
      action-label="创建任务"
      action-href="./task-studio.html"
    />
  </div>

  <div v-else class="surface-base overflow-hidden">
    <div class="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow class="hover:bg-transparent border-b border-border">
            <TableHead class="w-12 px-4 h-12">
              <Checkbox 
                v-if="isClient"
                :checked="allSelected"
                @update:checked="handleSelectAll"
                class="cursor-pointer"
              />
            </TableHead>
            <TableHead class="whitespace-nowrap px-4 h-12 text-xs font-semibold text-muted-foreground uppercase tracking-wider w-32">
              任务ID
            </TableHead>
            <TableHead class="whitespace-nowrap px-4 h-12 text-xs font-semibold text-muted-foreground uppercase tracking-wider min-w-0 max-w-xs">
              任务名称
            </TableHead>
            <TableHead class="whitespace-nowrap px-4 h-12 text-xs font-semibold text-muted-foreground uppercase tracking-wider w-24">
              区域
            </TableHead>
            <TableHead class="whitespace-nowrap px-4 h-12 text-xs font-semibold text-muted-foreground uppercase tracking-wider w-28">
              任务类型
            </TableHead>
            <TableHead class="whitespace-nowrap px-4 h-12 text-xs font-semibold text-muted-foreground uppercase tracking-wider w-20">
              优先级
            </TableHead>
            <TableHead class="whitespace-nowrap px-4 h-12 text-xs font-semibold text-muted-foreground uppercase tracking-wider w-24">
              状态
            </TableHead>
            <TableHead class="whitespace-nowrap px-4 h-12 text-xs font-semibold text-muted-foreground uppercase tracking-wider w-32">
              执行时间
            </TableHead>
            <TableHead class="whitespace-nowrap px-4 h-12 text-xs font-semibold text-muted-foreground uppercase tracking-wider w-20">
              风险统计
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow 
            v-for="task in tasks"
            :key="task.id"
            class="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors cursor-pointer"
            @click="handleRowClick(task.id, $event)"
          >
            <TableCell class="px-4 py-3">
              <Checkbox 
                v-if="isClient"
                :checked="selectedTaskIds.has(task.id)"
                @update:checked="(checked) => handleCheckboxChange(task.id, checked)"
                class="cursor-pointer"
                @click.stop
              />
            </TableCell>
            <TableCell class="px-4 py-3 text-xs font-mono text-muted-foreground">
              {{ task.id }}
            </TableCell>
            <TableCell class="px-4 py-3 text-sm text-card-foreground truncate max-w-xs">
              {{ task.name }}
            </TableCell>
            <TableCell class="px-4 py-3 text-sm text-card-foreground">
              {{ getZoneName(task.zoneId) }}
            </TableCell>
            <TableCell class="px-4 py-3 text-sm text-card-foreground truncate max-w-xs">
              {{ getTemplateName(task.templateId) }}
            </TableCell>
            <TableCell class="px-4 py-3">
              <StatusBadge :status="task.priority" size="sm" />
            </TableCell>
            <TableCell class="px-4 py-3">
              <StatusBadge :status="task.status" size="sm" />
            </TableCell>
            <TableCell class="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
              {{ formatDate(task.createdAt) }}
            </TableCell>
            <TableCell class="px-4 py-3 text-xs">
              <div class="flex items-center gap-1">
                <span v-if="task.status === 'success'" class="text-[hsl(var(--success))]">
                  {{ task.riskCount ?? getTaskResult(task.id)?.highRiskCount ?? 0 }}
                </span>
                <span v-else class="text-muted-foreground">-</span>
              </div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
</template>
