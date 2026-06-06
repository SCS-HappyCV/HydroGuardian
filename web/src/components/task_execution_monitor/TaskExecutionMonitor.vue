<!-- 任务执行监控页：回放真实 API trace；仅在 mock 任务中使用本地模拟进度。 -->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { buildTaskLogsFromSnapshot, getSnapshotProgress } from '@/api/execution-display'
import * as TaskExecutionSnapshotService from '@/data/TaskExecutionSnapshotService'
import * as TaskService from '@/data/TaskService'
import { queryByTaskId as getTaskLogs } from '@/data/TaskLogService'
import type { TaskData } from '@/data/TaskData'
import type { TaskLogData } from '@/data/TaskLogData'
import type { TaskExecutionSnapshot } from '@/lib/api-contracts'
import TaskInfoCard from './TaskInfoCard.vue'
import ExecutionLogStream from './ExecutionLogStream.vue'
import ProgressIndicator from './ProgressIndicator.vue'
import ActionButtons from './ActionButtons.vue'
import ApiSnapshotPanel from './ApiSnapshotPanel.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'

const isClient = ref(true)
const notFound = ref(false)
const taskId = ref<string>('')
const task = ref<TaskData | null>(null)
const logs = ref<TaskLogData[]>([])
const snapshot = ref<TaskExecutionSnapshot | null>(null)
const simulationInterval = ref<ReturnType<typeof window.setInterval> | null>(null)

// 计算当前任务状态，供进度条和操作按钮统一消费。
const taskStatus = computed(() => task.value?.status || 'queued')

// 计算当前任务进度；真实快照存在时按 trace 阶段映射，不走随机增长。
const taskProgress = computed(() => {
  return snapshot.value ? getSnapshotProgress(snapshot.value) : task.value?.progress || 0
})

// 判断任务是否正在运行。
const isRunning = computed(() => taskStatus.value === 'running')

// 判断任务是否成功完成。
const isSuccess = computed(() => taskStatus.value === 'success')

// 判断任务是否执行失败。
const isFailed = computed(() => taskStatus.value === 'failed')

// 判断任务是否仍在队列中。
const isQueued = computed(() => taskStatus.value === 'queued')

// 从 URL 查询参数中读取 taskId。
function getTaskIdFromUrl(): string {
  if (typeof window === 'undefined') return ''
  const params = new URLSearchParams(window.location.search)
  return params.get('taskId') || ''
}

// 将真实执行快照的终态映射到当前本地任务状态。
function resolveTaskStatusFromSnapshot(value: TaskExecutionSnapshot): TaskData['status'] {
  const status = value.executionStatus.trim().toUpperCase()
  if (status === 'FAILED' || status === 'ERROR' || status === 'ABSTAINED') return 'failed'
  if (status === 'SUCCESS' || status === 'SUCCEEDED' || status === 'COMPLETED' || status === 'DONE' || status === 'REVIEW_REQUIRED') return 'success'
  return value.errorCount > 0 ? 'failed' : 'success'
}

// 用真实执行快照修正本地任务状态和进度。
function applySnapshotToTask(baseTask: TaskData, value: TaskExecutionSnapshot): TaskData {
  const completedAt = baseTask.finishedAt || value.createdAt
  return {
    ...baseTask,
    status: resolveTaskStatusFromSnapshot(value),
    progress: getSnapshotProgress(value),
    finishedAt: completedAt,
    updatedAt: completedAt,
  }
}

// 将当前任务状态写回本地存储，保证刷新或跳转后状态连续。
function persistCurrentTask(): void {
  if (!task.value) return
  const allTasks = [...TaskService.getAll()]
  const index = allTasks.findIndex((item) => item.id === task.value?.id)

  if (index >= 0) {
    allTasks[index] = { ...task.value }
    TaskService.savePersisted(allTasks)
  }
}

// 初始化任务、日志和 API 快照；没有 URL taskId 时回退到一个演示任务。
function initializeTask(): void {
  const urlTaskId = getTaskIdFromUrl()
  taskId.value = urlTaskId || 'task-1001'

  const fetchedTask = TaskService.getById(taskId.value)
  if (!fetchedTask) {
    notFound.value = true
    return
  }

  snapshot.value = TaskExecutionSnapshotService.getByTaskId(taskId.value) ?? null

  if (snapshot.value) {
    task.value = applySnapshotToTask(fetchedTask, snapshot.value)
    logs.value = buildTaskLogsFromSnapshot(snapshot.value)
    persistCurrentTask()
    return
  }

  task.value = { ...fetchedTask }
  logs.value = getTaskLogs(taskId.value)
}

// 启动本地演示进度模拟；真实 API 快照存在时不再模拟。
function startSimulation(): void {
  if (!isRunning.value || simulationInterval.value || snapshot.value) return

  simulationInterval.value = window.setInterval(() => {
    if (!task.value) return

    task.value.progress = Math.min(task.value.progress + Math.random() * 15, 95)

    if (task.value.progress >= 90 && Math.random() > 0.6) {
      task.value.progress = 100
      task.value.status = 'success'
      task.value.finishedAt = new Date().toISOString()
      task.value.updatedAt = task.value.finishedAt

      logs.value.push({
        id: `log-${Date.now()}`,
        taskId: task.value.id,
        level: 'info',
        message: '任务执行完成，已生成风险结果。',
        stepName: '完成',
        createdAt: new Date().toISOString(),
      })

      persistCurrentTask()

      if (simulationInterval.value) {
        window.clearInterval(simulationInterval.value)
        simulationInterval.value = null
      }

      toast.success('任务执行成功')
      return
    }

    const messages = [
      '正在处理数据...',
      '模型推理中...',
      '生成风险评分...',
      '汇总结果...',
      '准备输出...',
    ]
    const randomMessage = messages[Math.floor(Math.random() * messages.length)]

    logs.value.push({
      id: `log-${Date.now()}`,
      taskId: task.value.id,
      level: 'info',
      message: randomMessage,
      stepName: '执行中',
      createdAt: new Date().toISOString(),
    })

    task.value.updatedAt = new Date().toISOString()
    persistCurrentTask()
  }, 2000)
}

// 停止当前运行任务，并记录用户中断日志。
function handleStop(): void {
  if (!task.value) return

  task.value.status = 'failed'
  task.value.finishedAt = new Date().toISOString()
  task.value.updatedAt = task.value.finishedAt

  logs.value.push({
    id: `log-${Date.now()}`,
    taskId: task.value.id,
    level: 'error',
    message: '任务已被用户中断。',
    stepName: '中断',
    createdAt: new Date().toISOString(),
  })

  if (simulationInterval.value) {
    window.clearInterval(simulationInterval.value)
    simulationInterval.value = null
  }

  persistCurrentTask()
  toast.success('任务已停止')
}

// 重新执行任务；重试时清理旧 API 快照，防止监控页展示过期结果。
function handleRetry(): void {
  if (!task.value) return

  TaskExecutionSnapshotService.removeByTaskId(task.value.id)
  snapshot.value = null
  task.value.status = 'queued'
  task.value.progress = 0
  task.value.startedAt = undefined
  task.value.finishedAt = undefined
  task.value.updatedAt = new Date().toISOString()
  logs.value = [
    {
      id: `log-${Date.now()}`,
      taskId: task.value.id,
      level: 'info',
      message: '任务已重新加入执行队列。',
      stepName: '排队',
      createdAt: new Date().toISOString(),
    },
  ]

  persistCurrentTask()
  toast.success('任务已重新加入队列')

  window.setTimeout(() => {
    if (!task.value) return
    task.value.status = 'running'
    task.value.startedAt = new Date().toISOString()
    task.value.progress = 5
    task.value.updatedAt = task.value.startedAt
    persistCurrentTask()
    startSimulation()
  }, 1000)
}

// 跳回任务工作坊并携带当前 taskId，便于继续修改参数。
function handleModifyParams(): void {
  window.location.href = `./task-studio.html?taskId=${taskId.value}`
}

// 跳转风险工作台查看任务结果。
function handleViewResults(): void {
  window.location.href = `./risk-workspace.html?taskId=${taskId.value}`
}

// 跳转系统健康页排查执行失败原因。
function handleViewSystemHealth(): void {
  window.location.href = './system-health.html'
}

// 组件挂载后初始化任务，并在本地演示运行态时启动模拟器。
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

// 组件卸载时清理定时器，避免页面切换后继续推日志。
onUnmounted(() => {
  if (simulationInterval.value) {
    window.clearInterval(simulationInterval.value)
  }
})

// 监听任务状态变化，运行态启动模拟器，非运行态清理模拟器。
watch(() => taskStatus.value, (newStatus) => {
  if (newStatus === 'running' && !simulationInterval.value) {
    startSimulation()
  } else if (newStatus !== 'running' && simulationInterval.value) {
    window.clearInterval(simulationInterval.value)
    simulationInterval.value = null
  }
})
</script>

<template>
  <div v-if="isClient && task" class="page-body space-y-6 pb-12">
    <div class="flex items-center justify-between gap-4 mb-6">
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

    <ApiSnapshotPanel v-if="snapshot" :snapshot="snapshot" />

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

  <div v-else-if="isClient && notFound" class="page-body flex min-h-screen items-center justify-center">
    <div class="surface-base card-padding max-w-md text-center space-y-3">
      <SafeIcon name="SearchX" :size="36" class="mx-auto text-muted-foreground" />
      <h1 class="text-item-title">未找到任务</h1>
      <p class="text-sm text-muted-foreground">当前 taskId 不存在，请返回任务工作坊重新创建任务。</p>
      <a href="./task-studio.html" class="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary-hover">
        返回任务工作坊
      </a>
    </div>
  </div>

  <div v-else class="h-screen flex items-center justify-center">
    <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
  </div>
</template>
