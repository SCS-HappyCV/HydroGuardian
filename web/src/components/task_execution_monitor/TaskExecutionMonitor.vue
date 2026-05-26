
<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { toast } from 'vue-sonner'
import { getById as getTaskById } from '@/data/TaskService'
import { queryByTaskId as getTaskLogs } from '@/data/TaskLogService'
import { getByTaskIdVO as getTaskResult } from '@/data/TaskResultService'
import type { TaskData } from '@/data/TaskData'
import type { TaskLogData } from '@/data/TaskLogData'
import TaskInfoCard from './TaskInfoCard.vue'
import ExecutionLogStream from './ExecutionLogStream.vue'
import ProgressIndicator from './ProgressIndicator.vue'
import ActionButtons from './ActionButtons.vue'

const isClient = ref(true)
const taskId = ref<string>('')
const task = ref<TaskData | null>(null)
const logs = ref<TaskLogData[]>([])
const result = ref<any>(null)
const simulationInterval = ref<NodeJS.Timeout | null>(null)

const taskStatus = computed(() => task.value?.status || 'queued')
const taskProgress = computed(() => task.value?.progress || 0)
const isRunning = computed(() => taskStatus.value === 'running')
const isSuccess = computed(() => taskStatus.value === 'success')
const isFailed = computed(() => taskStatus.value === 'failed')
const isQueued = computed(() => taskStatus.value === 'queued')

const getTaskIdFromUrl = (): string => {
  if (typeof window === 'undefined') return ''
  const params = new URLSearchParams(window.location.search)
  return params.get('taskId') || ''
}

const initializeTask = () => {
  const urlTaskId = getTaskIdFromUrl()
  if (urlTaskId) {
    taskId.value = urlTaskId
  } else {
    const allTasks = [
      { id: 'task-1001', status: 'success' },
      { id: 'task-1002', status: 'running' },
      { id: 'task-1003', status: 'failed' }
    ]
    taskId.value = allTasks[0].id
  }

  const fetchedTask = getTaskById(taskId.value)
  if (fetchedTask) {
    task.value = { ...fetchedTask }
    logs.value = getTaskLogs(taskId.value)
    result.value = getTaskResult(taskId.value)
  }
}

const startSimulation = () => {
  if (!isRunning.value || simulationInterval.value) return

  simulationInterval.value = setInterval(() => {
    if (task.value) {
      task.value.progress = Math.min(task.value.progress + Math.random() * 15, 95)
      
      if (task.value.progress >= 90 && Math.random() > 0.6) {
        task.value.progress = 100
        task.value.status = 'success'
        task.value.finishedAt = new Date().toISOString()
        
        logs.value.push({
          id: `log-${Date.now()}`,
          taskId: task.value.id,
          level: 'info',
          message: '任务执行完成，已生成风险结果。',
          stepName: '完成',
          createdAt: new Date().toISOString()
        })
        
        if (simulationInterval.value) {
          clearInterval(simulationInterval.value)
          simulationInterval.value = null
        }
        toast.success('任务执行成功')
      } else {
        const messages = [
          '正在处理数据...',
          '模型推理中...',
          '生成风险评分...',
          '汇总结果...',
          '准备输出...'
        ]
        const randomMsg = messages[Math.floor(Math.random() * messages.length)]
        logs.value.push({
          id: `log-${Date.now()}`,
          taskId: task.value.id,
          level: 'info',
          message: randomMsg,
          stepName: '执行中',
          createdAt: new Date().toISOString()
        })
      }
    }
  }, 2000)
}

const handleStop = () => {
  if (task.value) {
    task.value.status = 'failed'
    task.value.finishedAt = new Date().toISOString()
    
    logs.value.push({
      id: `log-${Date.now()}`,
      taskId: task.value.id,
      level: 'error',
      message: '任务已被用户中断。',
      stepName: '中断',
      createdAt: new Date().toISOString()
    })
    
    if (simulationInterval.value) {
      clearInterval(simulationInterval.value)
      simulationInterval.value = null
    }
    
    toast.success('任务已停止')
  }
}

const handleRetry = () => {
  if (task.value) {
    task.value.status = 'queued'
    task.value.progress = 0
    task.value.startedAt = undefined
    task.value.finishedAt = undefined
    logs.value = []
    
    logs.value.push({
      id: `log-${Date.now()}`,
      taskId: task.value.id,
      level: 'info',
      message: '任务已重新加入执行队列。',
      stepName: '排队',
      createdAt: new Date().toISOString()
    })
    
    toast.success('任务已重新加入队列')
    
    setTimeout(() => {
      if (task.value) {
        task.value.status = 'running'
        task.value.startedAt = new Date().toISOString()
        task.value.progress = 5
        startSimulation()
      }
    }, 1000)
  }
}

const handleModifyParams = () => {
  window.location.href = `./task-studio.html?taskId=${taskId.value}`
}

const handleViewResults = () => {
  window.location.href = `./risk-workspace.html?taskId=${taskId.value}`
}

const handleViewSystemHealth = () => {
  window.location.href = './system-health.html'
}

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    isClient.value = true
  })
  
  initializeTask()
  
  if (isRunning.value) {
    startSimulation()
  }
})

onUnmounted(() => {
  if (simulationInterval.value) {
    clearInterval(simulationInterval.value)
  }
})

watch(() => taskStatus.value, (newStatus) => {
  if (newStatus === 'running' && !simulationInterval.value) {
    startSimulation()
  } else if (newStatus !== 'running' && simulationInterval.value) {
    clearInterval(simulationInterval.value)
    simulationInterval.value = null
  }
})
</script>

<template>
  <div v-if="isClient && task" class="page-body space-y-6 pb-12">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-page-title">任务执行监控</h1>
        <p class="text-body mt-2">{{ task.name }}</p>
      </div>
      <a 
        href="./task-studio.html" 
        class="flex items-center gap-2 px-4 py-2 rounded-lg bg-muted/30 hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors"
      >
        <SafeIcon name="ArrowLeft" :size="16" />
        <span class="text-sm">返回任务工作坊</span>
      </a>
    </div>

    <TaskInfoCard :task="task" />

    <ProgressIndicator :progress="taskProgress" :status="taskStatus" />

    <ExecutionLogStream :logs="logs" />

    <ActionButtons
      :status="taskStatus"
      :is-running="isRunning"
      :is-success="isSuccess"
      :is-failed="isFailed"
      :is-queued="isQueued"
      @stop="handleStop"
      @retry="handleRetry"
      @modify-params="handleModifyParams"
      @view-results="handleViewResults"
      @view-system-health="handleViewSystemHealth"
    />
  </div>
  <div v-else class="h-screen flex items-center justify-center">
    <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
  </div>
</template>
