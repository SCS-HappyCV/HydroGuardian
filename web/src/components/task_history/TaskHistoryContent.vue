<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import { remoteAgentApi } from '@/api/remote-agent-api'
import * as TaskService from '@/data/TaskService'
import type { TaskData } from '@/data/TaskData'
import type { RemoteAgentJob, RemoteTaskRecord } from '@/lib/remote-agent-types'
import { mapRemoteTask, restoreRemoteTaskBinding } from '@/lib/remote-task-history'
import PageHeader from '@/components/common/PageHeader.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

type StatusFilter = 'all' | TaskData['status']

const tasks = ref<TaskData[]>([])
const remoteTaskIds = ref(new Set<string>())
const loading = ref(true)
const refreshing = ref(false)
const keyword = ref('')
const statusFilter = ref<StatusFilter>('all')
const taskPreviews = ref<Record<string, TaskPreview>>({})

interface TaskPreview {
  primaryUrl?: string
  beforeUrl?: string
  afterUrl?: string
  pointCloud: boolean
}

const statusOptions: Array<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'success', label: '已完成' },
  { value: 'running', label: '执行中' },
  { value: 'failed', label: '异常' },
  { value: 'queued', label: '等待中' },
]

const filteredTasks = computed(() => {
  const normalized = keyword.value.trim().toLowerCase()
  return tasks.value.filter((task) => {
    if (statusFilter.value !== 'all' && task.status !== statusFilter.value) return false
    if (!normalized) return true
    return [task.name, task.inputText, task.id, task.remoteJobId].some((value) => value?.toLowerCase().includes(normalized))
  })
})

const stats = computed(() => ({
  total: tasks.value.length,
  success: tasks.value.filter((task) => task.status === 'success').length,
  artifacts: tasks.value.reduce((sum, task) => sum + (task.artifactCount || 0), 0),
  risks: tasks.value.reduce((sum, task) => sum + (task.riskCount || 0), 0),
}))

function formatDate(value?: string) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function duration(task: TaskData) {
  if (!task.startedAt) return '未开始'
  const end = task.finishedAt ? new Date(task.finishedAt).getTime() : Date.now()
  const seconds = Math.max(0, Math.round((end - new Date(task.startedAt).getTime()) / 1000))
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  const remain = seconds % 60
  return minutes < 60 ? `${minutes} 分 ${remain} 秒` : `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`
}

function statusView(status: TaskData['status']) {
  return {
    success: { label: '分析完成', icon: 'CircleCheckBig', tone: 'border-emerald-300/20 bg-emerald-300/10 text-emerald-200', rail: 'bg-emerald-400' },
    running: { label: '正在执行', icon: 'LoaderCircle', tone: 'border-cyan-300/20 bg-cyan-300/10 text-cyan-200', rail: 'bg-cyan-400' },
    failed: { label: '执行异常', icon: 'TriangleAlert', tone: 'border-rose-300/20 bg-rose-300/10 text-rose-200', rail: 'bg-rose-400' },
    queued: { label: '等待调度', icon: 'Clock3', tone: 'border-amber-300/20 bg-amber-300/10 text-amber-200', rail: 'bg-amber-300' },
  }[status]
}

function artifactId(value: unknown) {
  if (typeof value !== 'string') return undefined
  return /^artifact:\/\/([A-Za-z0-9_-]+)$/.exec(value)?.[1]
}

function buildTaskPreview(job: RemoteAgentJob): TaskPreview {
  const assets = job.submission.assets || {}
  const beforeId = artifactId(assets.before_image_path)
  const afterId = artifactId(assets.after_image_path)
  const imageId = artifactId(assets.image_path)
  return {
    primaryUrl: afterId || imageId || beforeId ? remoteAgentApi.getPreviewUrl(afterId || imageId || beforeId || '') : undefined,
    beforeUrl: beforeId ? remoteAgentApi.getPreviewUrl(beforeId) : undefined,
    afterUrl: afterId ? remoteAgentApi.getPreviewUrl(afterId) : undefined,
    pointCloud: Boolean(artifactId(assets.point_cloud_path)),
  }
}

async function loadTaskPreviews(remoteTasks: RemoteTaskRecord[]) {
  taskPreviews.value = {}
  await Promise.all(remoteTasks.map(async (task) => {
    try {
      const job = await remoteAgentApi.getJob(task.job_id)
      taskPreviews.value = { ...taskPreviews.value, [task.task_id]: buildTaskPreview(job) }
    } catch {}
  }))
}

async function loadTasks(showFeedback = false) {
  if (showFeedback) refreshing.value = true
  try {
    const remoteTasks = await remoteAgentApi.listTasks({ limit: '500' })
    remoteTasks.forEach(restoreRemoteTaskBinding)
    remoteTaskIds.value = new Set(remoteTasks.map((task) => task.task_id))
    tasks.value = remoteTasks.map(mapRemoteTask)
      .sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime())
    void loadTaskPreviews(remoteTasks)
    if (showFeedback) toast.success('历史任务已同步')
  } catch (error) {
    tasks.value = TaskService.getAll().sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime())
    toast.error(error instanceof Error ? error.message : '历史任务同步失败')
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function openTask(task: TaskData) {
  window.location.href = remoteTaskIds.value.has(task.id)
    ? `./task-execution-monitor.html?taskId=${encodeURIComponent(task.id)}`
    : `./history-playback.html?taskId=${encodeURIComponent(task.id)}`
}

onMounted(() => { void loadTasks() })
</script>

<template>
  <div class="flex min-h-screen flex-col bg-background">
    <PageHeader title="历史任务" subtitle="查看全部已发起任务的执行轨迹、Agent 产物和可视化结果" :breadcrumb="[{ label: '首页', href: './dashboard.html' }, { label: '历史任务' }]">
      <template #actions><Button variant="outline" class="gap-2" :disabled="refreshing" @click="loadTasks(true)"><SafeIcon name="RefreshCw" :size="15" :class="refreshing ? 'animate-spin' : ''" />同步记录</Button></template>
    </PageHeader>

    <main class="flex-1 overflow-y-auto px-5 pb-8 pt-5 xl:px-7">
      <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <article v-for="item in [
          { label: '历史任务', value: stats.total, icon: 'ListVideo', color: 'text-cyan-200', surface: 'bg-cyan-300/10' },
          { label: '完成分析', value: stats.success, icon: 'CircleCheckBig', color: 'text-emerald-200', surface: 'bg-emerald-300/10' },
          { label: '证据产物', value: stats.artifacts, icon: 'Boxes', color: 'text-violet-200', surface: 'bg-violet-300/10' },
          { label: '风险候选', value: stats.risks, icon: 'ShieldAlert', color: 'text-orange-200', surface: 'bg-orange-300/10' },
        ]" :key="item.label" class="rounded-2xl border border-border/60 bg-card/35 p-4 shadow-sm">
          <div class="flex items-center justify-between"><div><p class="text-[11px] text-muted-foreground">{{ item.label }}</p><strong class="mt-2 block text-2xl font-semibold text-foreground">{{ item.value }}</strong></div><span class="grid h-10 w-10 place-items-center rounded-xl" :class="[item.surface, item.color]"><SafeIcon :name="item.icon" :size="19" /></span></div>
        </article>
      </section>

      <section class="mt-4 overflow-hidden rounded-2xl border border-border/60 bg-card/25">
        <header class="flex flex-col gap-3 border-b border-border/50 p-4 xl:flex-row xl:items-center xl:justify-between">
          <div><h2 class="text-sm font-semibold text-foreground">执行记录</h2><p class="mt-1 text-[11px] text-muted-foreground">点击任务可查看动态规划路径、专家执行、影像、点云与风险证据</p></div>
          <div class="flex flex-col gap-2 sm:flex-row">
            <div class="relative min-w-[280px]"><SafeIcon name="Search" :size="14" class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input v-model="keyword" class="h-9 pl-9" placeholder="搜索任务名称、指令或 ID" /></div>
            <div class="flex items-center gap-1 rounded-xl border border-border/60 bg-background/30 p-1"><button v-for="option in statusOptions" :key="option.value" type="button" class="rounded-lg px-3 py-1.5 text-[11px] transition" :class="statusFilter === option.value ? 'bg-cyan-300/12 text-cyan-200' : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground'" @click="statusFilter = option.value">{{ option.label }}</button></div>
          </div>
        </header>

        <div v-if="loading" class="space-y-3 p-4"><div v-for="index in 4" :key="index" class="h-32 animate-pulse rounded-2xl bg-muted/25" /></div>
        <div v-else-if="filteredTasks.length" class="divide-y divide-border/40">
          <button v-for="task in filteredTasks" :key="task.id" type="button" class="group relative grid w-full gap-4 overflow-hidden px-5 py-4 text-left transition hover:bg-cyan-300/[0.035] lg:grid-cols-[190px_minmax(260px,1.35fr)_minmax(170px,.65fr)_minmax(280px,1fr)_36px] lg:items-center" @click="openTask(task)">
            <span class="absolute inset-y-3 left-0 w-1 rounded-r-full" :class="statusView(task.status).rail" />
            <div class="relative h-28 overflow-hidden rounded-2xl border border-white/10 bg-[#07111f] shadow-[0_14px_35px_rgba(0,0,0,.2)]">
              <template v-if="taskPreviews[task.id]?.beforeUrl && taskPreviews[task.id]?.afterUrl">
                <img :src="taskPreviews[task.id].beforeUrl" alt="巡查前时相" class="absolute inset-y-0 left-0 h-full w-1/2 object-cover" loading="lazy" decoding="async">
                <img :src="taskPreviews[task.id].afterUrl" alt="巡查后时相" class="absolute inset-y-0 right-0 h-full w-1/2 object-cover" loading="lazy" decoding="async">
                <span class="absolute inset-y-0 left-1/2 w-px bg-cyan-100/80 shadow-[0_0_12px_#67e8f9]" />
                <span class="absolute bottom-2 left-2 rounded-md bg-black/65 px-1.5 py-1 text-[8px] text-white backdrop-blur">巡查前</span>
                <span class="absolute bottom-2 right-2 rounded-md bg-black/65 px-1.5 py-1 text-[8px] text-amber-100 backdrop-blur">巡查后</span>
              </template>
              <img v-else-if="taskPreviews[task.id]?.primaryUrl" :src="taskPreviews[task.id].primaryUrl" alt="任务真实影像" class="h-full w-full object-cover transition duration-500 group-hover:scale-105" loading="lazy" decoding="async">
              <div v-else-if="taskPreviews[task.id]?.pointCloud" class="absolute inset-0 grid place-items-center bg-[radial-gradient(circle_at_48%_42%,rgba(34,211,238,.16),transparent_36%),linear-gradient(145deg,#0b2132,#06101c)]"><div class="text-center"><SafeIcon name="Box" :size="28" class="mx-auto text-cyan-200/80" /><p class="mt-2 text-[9px] text-slate-400">三维点云任务</p></div><span class="absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(103,232,249,.25)_1px,transparent_1px),linear-gradient(90deg,rgba(103,232,249,.25)_1px,transparent_1px)] [background-size:18px_18px]" /></div>
              <div v-else class="absolute inset-0 grid place-items-center"><SafeIcon name="ImageOff" :size="24" class="text-slate-700" /></div>
              <div class="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#06101c]/55 via-transparent to-transparent" />
              <span v-if="taskPreviews[task.id]?.primaryUrl" class="absolute left-2 top-2 inline-flex items-center gap-1 rounded-md border border-emerald-300/15 bg-black/60 px-1.5 py-1 text-[8px] text-emerald-100 backdrop-blur"><i class="h-1.5 w-1.5 rounded-full bg-emerald-300" />真实影像</span>
            </div>
            <div class="min-w-0"><div class="flex flex-wrap items-center gap-2"><span class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] font-semibold" :class="statusView(task.status).tone"><SafeIcon :name="statusView(task.status).icon" :size="11" :class="task.status === 'running' ? 'animate-spin' : ''" />{{ statusView(task.status).label }}</span><span class="font-mono text-[9px] text-muted-foreground">{{ task.id }}</span></div><h3 class="mt-2 truncate text-sm font-semibold text-foreground group-hover:text-cyan-100">{{ task.name }}</h3><p class="mt-1 line-clamp-1 text-[11px] text-muted-foreground">{{ task.inputText }}</p></div>
            <div class="grid grid-cols-2 gap-2 text-[10px]"><div><span class="block text-muted-foreground">发起时间</span><strong class="mt-1 block font-medium text-foreground">{{ formatDate(task.createdAt) }}</strong></div><div><span class="block text-muted-foreground">执行用时</span><strong class="mt-1 block font-medium text-foreground">{{ duration(task) }}</strong></div><div class="col-span-2"><div class="h-1.5 overflow-hidden rounded-full bg-muted/50"><div class="h-full rounded-full bg-gradient-to-r from-cyan-400 to-emerald-400 transition-all" :style="{ width: `${task.progress}%` }" /></div><span class="mt-1 block text-right font-mono text-[9px] text-muted-foreground">{{ task.progress }}%</span></div></div>
            <div class="grid grid-cols-4 gap-2"><div v-for="metric in [{ label: '步骤', value: task.stepCount || 0, icon: 'Route' }, { label: '产物', value: task.artifactCount || 0, icon: 'Boxes' }, { label: '风险', value: task.riskCount || 0, icon: 'ShieldAlert' }, { label: '工单', value: task.workorderCount || 0, icon: 'ClipboardCheck' }]" :key="metric.label" class="rounded-xl border border-border/50 bg-background/25 px-2 py-2 text-center"><SafeIcon :name="metric.icon" :size="12" class="mx-auto text-muted-foreground" /><strong class="mt-1 block text-sm text-foreground">{{ metric.value }}</strong><span class="text-[9px] text-muted-foreground">{{ metric.label }}</span></div></div>
            <span class="grid h-9 w-9 place-items-center rounded-xl border border-border/60 text-muted-foreground transition group-hover:border-cyan-300/30 group-hover:bg-cyan-300/10 group-hover:text-cyan-200"><SafeIcon name="ArrowUpRight" :size="15" /></span>
          </button>
        </div>
        <div v-else class="grid min-h-72 place-items-center p-8 text-center"><div><SafeIcon name="ListX" :size="34" class="mx-auto text-muted-foreground/50" /><p class="mt-3 text-sm text-foreground">没有匹配的历史任务</p><p class="mt-1 text-[11px] text-muted-foreground">请调整搜索内容或状态筛选</p></div></div>
      </section>
    </main>
  </div>
</template>
