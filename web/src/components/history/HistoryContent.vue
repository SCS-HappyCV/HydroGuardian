
<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import * as TaskService from '@/data/TaskService'
import * as TaskResultService from '@/data/TaskResultService'
import * as RiskEventService from '@/data/RiskEventService'
import * as ZoneService from '@/data/ZoneService'
import * as TaskTemplateService from '@/data/TaskTemplateService'
import PageHeader from '@/components/common/PageHeader.vue'
import HistoryFilterBar from './HistoryFilterBar.vue'
import HistoryTaskList from './HistoryTaskList.vue'
import HistoryComparisonModal from './HistoryComparisonModal.vue'
import { Button } from '@/components/ui/button'
import { toast } from 'vue-sonner'
import SafeIcon from '@/components/common/SafeIcon.vue'

const isClient = ref(true)

const allTasks = ref(TaskService.getAll())
const selectedTaskIds = ref<Set<string>>(new Set())
const showComparisonModal = ref(false)

const filters = ref({
  timeRange: 'all',
  zoneId: 'all',
  taskType: 'all'
})

const timeRangeOptions = [
  { value: 'all', label: '全部时间' },
  { value: 'today', label: '今天' },
  { value: 'week', label: '本周' },
  { value: 'month', label: '本月' },
  { value: 'older', label: '更早' }
]

const zoneOptions = computed(() => {
  const zones = ZoneService.getAll()
  return [
    { value: 'all', label: '全部区域' },
    ...zones.map(z => ({ value: z.id, label: z.name }))
  ]
})

const taskTypeOptions = computed(() => {
  const templates = TaskTemplateService.getAll()
  return [
    { value: 'all', label: '全部类型' },
    ...templates.map(t => ({ value: t.id, label: t.name }))
  ]
})

const filteredTasks = computed(() => {
  let result = allTasks.value

  if (filters.value.timeRange !== 'all') {
    const now = new Date('2026-05-25T00:00:00Z')
    result = result.filter(task => {
      const taskDate = new Date(task.createdAt)
      const daysDiff = Math.floor((now.getTime() - taskDate.getTime()) / (1000 * 60 * 60 * 24))
      
      switch (filters.value.timeRange) {
        case 'today':
          return daysDiff === 0
        case 'week':
          return daysDiff <= 7
        case 'month':
          return daysDiff <= 30
        case 'older':
          return daysDiff > 30
        default:
          return true
      }
    })
  }

  if (filters.value.zoneId !== 'all') {
    result = result.filter(task => task.zoneId === filters.value.zoneId)
  }

  if (filters.value.taskType !== 'all') {
    result = result.filter(task => task.templateId === filters.value.taskType)
  }

  return result.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
})

const canCompare = computed(() => selectedTaskIds.value.size === 2)

const handleTaskSelect = (taskId: string, selected: boolean) => {
  if (selected) {
    selectedTaskIds.value.add(taskId)
  } else {
    selectedTaskIds.value.delete(taskId)
  }
}

const handleCompare = () => {
  if (selectedTaskIds.value.size !== 2) {
    toast.error('请选择两个任务进行对比')
    return
  }
  const taskIds = Array.from(selectedTaskIds.value)
  const url = `./history-contrast.html?taskIds=${taskIds.join(',')}`
  window.location.href = url
}

const handleTaskRowClick = (taskId: string) => {
  window.location.href = `./history-playback.html?taskId=${taskId}`
}

const handleFilterChange = (newFilters: typeof filters.value) => {
  filters.value = newFilters
  selectedTaskIds.value.clear()
}

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    isClient.value = true
  })
})
</script>

<template>
  <div class="flex flex-col min-h-screen bg-background">
    <PageHeader 
      title="历史回放与对比"
      subtitle="查看历史任务执行记录，支持多维度筛选和结果对比"
      :breadcrumb="[
        { label: '首页', href: './dashboard.html' },
        { label: '历史回放与对比' }
      ]"
    >
      <template #actions>
        <Button 
          v-if="isClient"
          :disabled="!canCompare"
          class="gap-2"
          @click="handleCompare"
        >
          <SafeIcon name="GitCompare" :size="16" />
          对比选中任务
        </Button>
      </template>
    </PageHeader>

    <div class="flex-1 overflow-y-auto min-h-0 page-body">
      <div class="space-y-4">
        <HistoryFilterBar 
          :model-value="filters"
          :time-range-options="timeRangeOptions"
          :zone-options="zoneOptions"
          :task-type-options="taskTypeOptions"
          @update:model-value="handleFilterChange"
        />

        <HistoryTaskList 
          :tasks="filteredTasks"
          :selected-task-ids="selectedTaskIds"
          :is-client="isClient"
          @task-select="handleTaskSelect"
          @task-row-click="handleTaskRowClick"
        />
      </div>
    </div>
  </div>
</template>
