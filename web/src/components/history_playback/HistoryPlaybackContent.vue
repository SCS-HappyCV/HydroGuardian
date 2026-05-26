
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Slider } from '@/components/ui/slider'
import SafeIcon from '@/components/common/SafeIcon.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import Breadcrumb from '@/components/common/Breadcrumb.vue'
import { toast } from 'vue-sonner'
import { cn } from '@/lib/utils'
import * as TaskService from '@/data/TaskService'
import * as TaskLogService from '@/data/TaskLogService'
import * as RiskEventService from '@/data/RiskEventService'
import * as TaskResultService from '@/data/TaskResultService'
import type { TaskData } from '@/data/TaskData'
import type { TaskLogData } from '@/data/TaskLogData'
import type { RiskEventData } from '@/data/RiskEventData'

const allTasks = TaskService.getAll()
const defaultTask = allTasks.find(t => t.status === 'success') || allTasks[0]
const defaultTaskId = defaultTask?.id || 'task-1001'

const taskId = ref(defaultTaskId)
const task = ref<TaskData | undefined>(TaskService.getById(taskId.value))
const taskLogs = ref<TaskLogData[]>(TaskLogService.queryByTaskId(taskId.value))
const riskEvents = ref<RiskEventData[]>(RiskEventService.query({ filter: { taskId: taskId.value } }))
const taskResult = ref(TaskResultService.getByTaskIdVO(taskId.value))

const isClient = ref(true)
const activeTab = ref('logs')
const playbackProgress = ref(0)
const isPlaying = ref(false)

const breadcrumbItems = [
  { label: '全局总览', href: './dashboard.html' },
  { label: '历史回溯', href: './history.html' },
  { label: '任务回放' }
]

const taskStatusLabel = computed(() => {
  const statusMap: Record<string, string> = {
    queued: '排队中',
    running: '执行中',
    success: '成功',
    failed: '失败'
  }
  return statusMap[task.value?.status || 'unknown'] || '未知'
})

const taskDurationMs = computed(() => {
  if (!task.value?.startedAt || !task.value?.finishedAt) return 0
  return new Date(task.value.finishedAt).getTime() - new Date(task.value.startedAt).getTime()
})

const taskDurationSeconds = computed(() => Math.round(taskDurationMs.value / 1000))

const logsByStep = computed(() => {
  const grouped: Record<string, TaskLogData[]> = {}
  taskLogs.value.forEach(log => {
    if (!grouped[log.stepName]) grouped[log.stepName] = []
    grouped[log.stepName].push(log)
  })
  return grouped
})

const riskSummary = computed(() => {
  if (!taskResult.value) return { high: 0, medium: 0, low: 0, review: 0 }
  return {
    high: taskResult.value.highRiskCount || 0,
    medium: taskResult.value.mediumRiskCount || 0,
    low: taskResult.value.lowRiskCount || 0,
    review: taskResult.value.reviewRequiredCount || 0
  }
})

const handlePlaybackChange = (value: number[]) => {
  playbackProgress.value = value[0]
}

const togglePlayback = () => {
  isPlaying.value = !isPlaying.value
  if (isPlaying.value) {
    toast.success('回放已启动')
    const interval = setInterval(() => {
      playbackProgress.value += 1
      if (playbackProgress.value >= 100) {
        playbackProgress.value = 100
        isPlaying.value = false
        clearInterval(interval)
        toast.success('回放已完成')
      }
    }, 100)
  }
}

const handleExportLog = () => {
  toast.success('执行日志已导出为 CSV 文件')
}

const handleViewRisk = (riskId: string) => {
  window.location.href = `./workorder-center.html?riskId=${riskId}`
}

const handleBackToHistory = () => {
  window.location.href = './history.html'
}

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    const params = new URLSearchParams(window.location.search)
    const urlTaskId = params.get('taskId')
    if (urlTaskId) {
      taskId.value = urlTaskId
      const newTask = TaskService.getById(urlTaskId)
      if (newTask) {
        task.value = newTask
        taskLogs.value = TaskLogService.queryByTaskId(urlTaskId)
        riskEvents.value = RiskEventService.query({ filter: { taskId: urlTaskId } })
        taskResult.value = TaskResultService.getByTaskIdVO(urlTaskId)
      }
    }
    isClient.value = true
  })
})
</script>

<template>
  <div v-if="isClient" class="flex flex-col h-full min-h-0 bg-background">
    <PageHeader 
      title="任务执行回放" 
      :subtitle="`任务 ID: ${task?.id}`"
      :breadcrumb="breadcrumbItems"
    >
      <template #actions>
        <Button 
          variant="outline" 
          size="sm"
          @click="handleBackToHistory"
          class="gap-2"
        >
          <SafeIcon name="ArrowLeft" :size="16" />
          返回历史中心
        </Button>
      </template>
    </PageHeader>

    <div class="flex-1 overflow-y-auto min-h-0 page-body space-y-6">
      <!-- Task Overview Card -->
      <Card v-if="task" class="surface-base border-border">
        <CardHeader class="pb-3">
          <div class="flex items-start justify-between gap-4">
            <div class="space-y-2">
              <CardTitle class="text-xl">{{ task.name }}</CardTitle>
              <CardDescription class="text-sm">
                {{ task.inputText }}
              </CardDescription>
            </div>
            <StatusBadge :status="task.status" size="lg" />
          </div>
        </CardHeader>
        <Separator class="opacity-30" />
        <CardContent class="pt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="space-y-1">
            <p class="text-xs text-muted-foreground uppercase tracking-wider font-medium">优先级</p>
            <Badge :class="cn(
              'w-fit',
              task.priority === 'high' ? 'bg-destructive/20 text-destructive' :
              task.priority === 'medium' ? 'bg-[hsl(var(--warning))]/20 text-[hsl(var(--warning))]' :
              'bg-[hsl(var(--success))]/20 text-[hsl(var(--success))]'
            )">
              {{ task.priority === 'high' ? '高' : task.priority === 'medium' ? '中' : '低' }}
            </Badge>
          </div>
          <div class="space-y-1">
            <p class="text-xs text-muted-foreground uppercase tracking-wider font-medium">执行耗时</p>
            <p class="text-sm font-semibold text-foreground">{{ taskDurationSeconds }}s</p>
          </div>
          <div class="space-y-1">
            <p class="text-xs text-muted-foreground uppercase tracking-wider font-medium">开始时间</p>
            <p class="text-sm font-mono text-card-foreground">
              {{ task.startedAt ? new Date(task.startedAt).toLocaleString('zh-CN') : '-' }}
            </p>
          </div>
          <div class="space-y-1">
            <p class="text-xs text-muted-foreground uppercase tracking-wider font-medium">完成时间</p>
            <p class="text-sm font-mono text-card-foreground">
              {{ task.finishedAt ? new Date(task.finishedAt).toLocaleString('zh-CN') : '-' }}
            </p>
          </div>
        </CardContent>
      </Card>

      <!-- Playback Timeline -->
      <Card class="surface-base border-border">
        <CardHeader class="pb-3">
          <div class="flex items-center justify-between gap-4">
            <CardTitle class="text-lg">执行时间轴</CardTitle>
            <div class="flex items-center gap-2">
              <Button 
                variant="outline" 
                size="sm"
                @click="togglePlayback"
                class="gap-2"
              >
                <SafeIcon :name="isPlaying ? 'Pause' : 'Play'" :size="16" />
                {{ isPlaying ? '暂停' : '播放' }}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="space-y-2">
            <div class="flex items-center justify-between text-xs text-muted-foreground">
              <span>进度</span>
              <span>{{ playbackProgress }}%</span>
            </div>
            <Slider 
              :model-value="[playbackProgress]"
              :max="100"
              :step="1"
              class="w-full"
              @update:model-value="handlePlaybackChange"
            />
          </div>
          <div class="text-xs text-muted-foreground text-center">
            {{ Math.round(taskDurationSeconds * playbackProgress / 100) }}s / {{ taskDurationSeconds }}s
          </div>
        </CardContent>
      </Card>

      <!-- Tabs: Logs, Results, Risk Events -->
      <Tabs :value="activeTab" @update:value="(v) => activeTab = v" class="w-full">
        <TabsList class="grid w-full grid-cols-3 bg-card/50 border border-border">
          <TabsTrigger value="logs" class="gap-2">
            <SafeIcon name="FileText" :size="16" />
            <span class="hidden sm:inline">执行日志</span>
          </TabsTrigger>
          <TabsTrigger value="results" class="gap-2">
            <SafeIcon name="BarChart3" :size="16" />
            <span class="hidden sm:inline">执行结果</span>
          </TabsTrigger>
          <TabsTrigger value="risks" class="gap-2">
            <SafeIcon name="AlertTriangle" :size="16" />
            <span class="hidden sm:inline">风险事件</span>
            <Badge v-if="riskEvents.length > 0" variant="secondary" class="ml-1 bg-primary/20 text-primary border-primary/20">
              {{ riskEvents.length }}
            </Badge>
          </TabsTrigger>
        </TabsList>

        <!-- Logs Tab -->
        <TabsContent value="logs" class="space-y-4 mt-4">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-foreground">步骤日志流</h3>
            <Button 
              variant="outline" 
              size="sm"
              @click="handleExportLog"
              class="gap-2"
            >
              <SafeIcon name="Download" :size="14" />
              导出日志
            </Button>
          </div>

          <div class="space-y-4">
            <div v-for="(logs, stepName) in logsByStep" :key="stepName" class="space-y-2">
              <div class="flex items-center gap-2 px-3 py-2 bg-muted/30 rounded-md border border-border/50">
                <SafeIcon name="ChevronRight" :size="14" class="text-muted-foreground" />
                <span class="text-sm font-semibold text-foreground">{{ stepName }}</span>
                <Badge variant="outline" class="ml-auto text-[10px]">{{ logs.length }} 条</Badge>
              </div>

              <div class="space-y-1 pl-4 border-l-2 border-border/50">
                <div 
                  v-for="log in logs" 
                  :key="log.id"
                  :class="cn(
                    'log-entry',
                    log.level === 'info' && 'log-entry-info',
                    log.level === 'error' && 'log-entry-error',
                    log.level === 'warn' && 'log-entry-warning',
                    log.level === 'success' && 'log-entry-success'
                  )"
                >
                  <div class="flex items-start gap-2">
                    <SafeIcon 
                      :name="log.level === 'error' ? 'AlertCircle' : log.level === 'warn' ? 'AlertTriangle' : 'CheckCircle2'"
                      :size="12"
                      class="mt-0.5 shrink-0"
                    />
                    <div class="flex-1 min-w-0">
                      <p class="text-xs leading-relaxed break-words">{{ log.message }}</p>
                      <p class="text-[9px] text-muted-foreground/60 mt-0.5">
                        {{ new Date(log.createdAt).toLocaleTimeString('zh-CN') }}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </TabsContent>

        <!-- Results Tab -->
        <TabsContent value="results" class="space-y-4 mt-4">
          <Card v-if="taskResult" class="surface-base border-border">
            <CardHeader>
              <CardTitle class="text-lg">执行结果摘要</CardTitle>
            </CardHeader>
            <CardContent class="space-y-4">
              <p class="text-sm text-card-foreground leading-relaxed">
                {{ taskResult.summary }}
              </p>

              <Separator class="opacity-30" />

              <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div class="space-y-2 p-3 bg-destructive/10 rounded-lg border border-destructive/20">
                  <p class="text-xs text-muted-foreground uppercase tracking-wider font-medium">高风险</p>
                  <p class="text-2xl font-bold text-destructive">{{ riskSummary.high }}</p>
                </div>
                <div class="space-y-2 p-3 bg-[hsl(var(--warning))]/10 rounded-lg border border-[hsl(var(--warning))]/20">
                  <p class="text-xs text-muted-foreground uppercase tracking-wider font-medium">中风险</p>
                  <p class="text-2xl font-bold text-[hsl(var(--warning))]">{{ riskSummary.medium }}</p>
                </div>
                <div class="space-y-2 p-3 bg-[hsl(var(--success))]/10 rounded-lg border border-[hsl(var(--success))]/20">
                  <p class="text-xs text-muted-foreground uppercase tracking-wider font-medium">低风险</p>
                  <p class="text-2xl font-bold text-[hsl(var(--success))]">{{ riskSummary.low }}</p>
                </div>
                <div class="space-y-2 p-3 bg-accent/10 rounded-lg border border-accent/20">
                  <p class="text-xs text-muted-foreground uppercase tracking-wider font-medium">待复核</p>
                  <p class="text-2xl font-bold text-accent">{{ riskSummary.review }}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <div v-else class="text-center py-12 text-muted-foreground">
            <SafeIcon name="Inbox" :size="32" class="mx-auto mb-2 opacity-30" />
            <p class="text-sm">暂无执行结果</p>
          </div>
        </TabsContent>

        <!-- Risk Events Tab -->
        <TabsContent value="risks" class="space-y-4 mt-4">
          <div v-if="riskEvents.length > 0" class="space-y-3">
            <div 
              v-for="risk in riskEvents" 
              :key="risk.id"
              class="risk-card"
              :class="cn(
                risk.level === 'high' && 'risk-card-high',
                risk.level === 'medium' && 'risk-card-medium',
                risk.level === 'low' && 'risk-card-low'
              )"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-1">
                    <h4 class="text-sm font-semibold text-foreground truncate">{{ risk.title }}</h4>
                    <StatusBadge :status="risk.level" size="sm" />
                  </div>
                  <p class="text-xs text-muted-foreground leading-relaxed">{{ risk.description }}</p>
                  <p class="text-[10px] text-muted-foreground/60 mt-2">
                    证据: {{ risk.evidenceSummary }}
                  </p>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                  <div class="text-right">
                    <p class="text-xs text-muted-foreground">风险分数</p>
                    <p class="text-lg font-bold text-foreground">{{ risk.score }}</p>
                  </div>
                  <Button 
                    variant="ghost" 
                    size="icon"
                    class="h-8 w-8"
                    @click="handleViewRisk(risk.id)"
                    title="查看工单"
                  >
                    <SafeIcon name="ExternalLink" :size="14" />
                  </Button>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="text-center py-12 text-muted-foreground">
            <SafeIcon name="CheckCircle2" :size="32" class="mx-auto mb-2 opacity-30" />
            <p class="text-sm">未发现风险事件</p>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  </div>

  <div v-else class="h-full flex items-center justify-center bg-background">
    <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
  </div>
</template>
