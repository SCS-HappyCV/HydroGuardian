<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import * as TaskService from '@/data/TaskService'
import type { TaskData } from '@/data/TaskData'
import TaskInfoCard from './TaskInfoCard.vue'
import ActionButtons from './ActionButtons.vue'
import DynamicWorkflowGraph from './DynamicWorkflowGraph.vue'
import SpatialPositionCard from './SpatialPositionCard.vue'
import AgentArtifactFeed from './AgentArtifactFeed.vue'
import LanguageExpertResultCard from './LanguageExpertResultCard.vue'
import SemanticSceneResultCard from './SemanticSceneResultCard.vue'
import GeometryRelationResultCard from './GeometryRelationResultCard.vue'
import QualityVerificationResultCard from './QualityVerificationResultCard.vue'
import AgentPlaybackControls from './AgentPlaybackControls.vue'
import ExecutionStatusHero from './ExecutionStatusHero.vue'
import RealtimeExecutionFeed from './RealtimeExecutionFeed.vue'
import AgentResultVisualization from './AgentResultVisualization.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { competitionDemo } from '@/data/CompetitionDemoData'
import { localAgentRuntime } from '@/lib/local-agent-runtime'
import { remoteAgentProvider } from '@/lib/remote-agent-provider'
import type { RemoteStreamState } from '@/lib/remote-agent-provider'
import { getRemoteAgentBinding, getRemoteAgentSnapshot } from '@/lib/remote-agent-storage'
import { remoteAgentApi } from '@/api/remote-agent-api'
import type { AgentExecutionStatus, AgentPresentationSnapshot } from '@/lib/agent-presentation-types'
import type { RemoteAgentMessage } from '@/lib/remote-agent-types'
import { mapRemoteTask, restoreRemoteTaskBinding } from '@/lib/remote-task-history'

type LocalAgentPageStatus = AgentExecutionStatus | 'missing_plan'

const isClient = ref(false)
const notFound = ref(false)
const taskId = ref('')
const task = ref<TaskData | null>(null)
const snapshot = ref<AgentPresentationSnapshot | null>(null)
const showTechnicalDetails = ref(false)
const unsubscribe = ref<(() => void) | null>(null)
const providerMode = ref<'local' | 'remote'>('local')
const loadError = ref('')
const isReloading = ref(false)
const streamState = ref<RemoteStreamState>('connecting')
const messages = ref<RemoteAgentMessage[]>([])
const isSendingMessage = ref(false)
const awaitingAgentReply = ref(false)
const messageApiAvailable = ref(true)
let lastConversationEventId = ''
let messagePollTimer: ReturnType<typeof setTimeout> | null = null
let messagePollAttempts = 0

const pageStatus = computed<LocalAgentPageStatus>(() => snapshot.value?.status || 'missing_plan')
const progress = computed(() => snapshot.value?.workflow?.progress ?? (['completed', 'review_required'].includes(pageStatus.value) ? 100 : 0))
const isRunning = computed(() => pageStatus.value === 'running' || pageStatus.value === 'preparing')
const isPaused = computed(() => pageStatus.value === 'paused')
const isTerminal = computed(() => ['completed', 'review_required', 'clarification_required', 'abstained', 'blocked', 'cancelled', 'failed'].includes(pageStatus.value))
const isSuccess = computed(() => ['completed', 'review_required'].includes(pageStatus.value))
const isFailed = computed(() => pageStatus.value === 'failed')
const isQueued = computed(() => pageStatus.value === 'idle' || pageStatus.value === 'preparing')
const canViewResults = computed(() => providerMode.value === 'local' || Boolean(snapshot.value?.business.risks.length))
const hasAnalysisResults = computed(() => Boolean(snapshot.value?.evidence.languageResult || snapshot.value?.evidence.semanticResult || snapshot.value?.evidence.geometryResult))
const hasSpatialResults = computed(() => Boolean(snapshot.value?.spatial))
const hasEvidenceResults = computed(() => Boolean(snapshot.value?.evidence.artifacts.length || snapshot.value?.quality.reports?.length))
const hasResultContent = computed(() => hasAnalysisResults.value || hasSpatialResults.value || hasEvidenceResults.value)
const hasVisualResult = computed(() => Boolean(
  snapshot.value?.evidence.artifacts.some((item) => (item.downloadUrl || item.previewUrl) && [
    'point_cloud_path',
    'before_image_path',
    'after_image_path',
    'image_path',
  ].includes(item.role)),
))
const defaultResultTab = computed(() => hasAnalysisResults.value ? 'analysis' : hasSpatialResults.value ? 'spatial' : 'evidence')
const qualityLabel = computed(() => ({ passed: '质量通过', limited: '结果受限', review_required: '建议复核', unavailable: '尚无结论' }[snapshot.value?.quality.verdict || 'unavailable']))

function getTaskIdFromUrl() {
  if (typeof window === 'undefined') return ''
  return new URLSearchParams(window.location.search).get('taskId') || ''
}

function persistTask() {
  if (!task.value) return
  try {
    const all = TaskService.getAll()
    const index = all.findIndex((item) => item.id === task.value?.id)
    if (index >= 0) {
      all[index] = { ...task.value }
      TaskService.savePersisted(all)
    }
  } catch {}
}

function syncTask(next: AgentPresentationSnapshot) {
  if (!task.value) return
  const succeeded = ['completed', 'review_required'].includes(next.status)
  const stopped = ['failed', 'blocked', 'cancelled'].includes(next.status)
  const terminal = succeeded || stopped || ['clarification_required', 'abstained'].includes(next.status)
  task.value = {
    ...task.value,
    status: stopped ? 'failed' : succeeded ? 'success' : next.status === 'idle' ? 'queued' : 'running',
    progress: next.workflow?.progress ?? (succeeded ? 100 : 0),
    finishedAt: terminal ? (task.value.finishedAt || new Date().toISOString()) : undefined,
    updatedAt: new Date().toISOString(),
  }
  persistTask()
}

function restoreCachedPreviewUrls(cached: AgentPresentationSnapshot): AgentPresentationSnapshot {
  const previewRoles = new Set(['before_image_path', 'after_image_path', 'image_path', 'change_mask', 'diagnostic_overlay'])
  return {
    ...cached,
    evidence: {
      ...cached.evidence,
      artifacts: cached.evidence.artifacts.map((artifact) => artifact.previewUrl || (!artifact.mediaType?.startsWith('image/') && !previewRoles.has(artifact.role))
        ? artifact
        : { ...artifact, previewUrl: remoteAgentApi.getPreviewUrl(artifact.artifactId) }),
    },
  }
}

async function initializeTask() {
  loadError.value = ''
  notFound.value = false
  unsubscribe.value?.()
  unsubscribe.value = null
  taskId.value = getTaskIdFromUrl() || competitionDemo.taskId || 'task-1001'
  let remoteTaskLoaded = false
  try {
    const remoteTask = await remoteAgentApi.getTask(taskId.value)
    task.value = mapRemoteTask(remoteTask)
    restoreRemoteTaskBinding(remoteTask)
    remoteTaskLoaded = true
  } catch {
    task.value = TaskService.getById(taskId.value) || null
  }
  if (!task.value) {
    notFound.value = true
    return
  }
  if (remoteTaskLoaded || getRemoteAgentBinding(taskId.value)) {
    providerMode.value = 'remote'
    const cached = getRemoteAgentSnapshot(taskId.value)
    if (cached) {
      snapshot.value = restoreCachedPreviewUrls(cached)
      syncTask(snapshot.value)
    }
    try {
      const refreshed = await remoteAgentProvider.restore(taskId.value)
      if (refreshed) snapshot.value = refreshed
    } catch (error) {
      if (!cached) {
        loadError.value = error instanceof Error ? error.message : '智能分析服务状态加载失败'
        toast.error(loadError.value)
      } else {
        toast.warning('已展示最近一次执行结果，最新状态暂未同步')
      }
    }
    await loadMessages()
  } else {
    snapshot.value = localAgentRuntime.restore(taskId.value) || null
  }
  if (!snapshot.value) return
  syncTask(snapshot.value)
  unsubscribe.value = providerMode.value === 'remote'
    ? (isTerminal.value ? (streamState.value = 'closed', null) : remoteAgentProvider.subscribe(taskId.value, handleSnapshot, (state) => { streamState.value = state }))
    : localAgentRuntime.subscribe(taskId.value, handleSnapshot)
}

async function loadMessages() {
  const binding = getRemoteAgentBinding(taskId.value)
  if (!binding || !messageApiAvailable.value) return
  try {
    const response = await remoteAgentApi.getMessages(binding.jobId)
    messages.value = response.messages
    awaitingAgentReply.value = response.pending
    if (response.pending) scheduleMessagePoll()
    else stopMessagePoll()
  } catch (error) {
    if (error instanceof Error && error.message.includes('404')) messageApiAvailable.value = false
  }
}

function stopMessagePoll() {
  if (messagePollTimer) clearTimeout(messagePollTimer)
  messagePollTimer = null
  messagePollAttempts = 0
}

function scheduleMessagePoll() {
  if (messagePollTimer) return
  const delay = messagePollAttempts < 150 ? 2000 : 10000
  messagePollTimer = setTimeout(async () => {
    messagePollTimer = null
    messagePollAttempts += 1
    await loadMessages()
  }, delay)
}

async function handleReload() {
  isReloading.value = true
  if (providerMode.value === 'remote') remoteAgentProvider.close(taskId.value)
  await initializeTask()
  isReloading.value = false
}

function handleSnapshot(next: AgentPresentationSnapshot) {
  snapshot.value = next
  syncTask(next)
  const latestConversation = [...next.trace].reverse().find((item) => item.stage === 'conversation_message')
  if (latestConversation && latestConversation.traceId !== lastConversationEventId) {
    lastConversationEventId = latestConversation.traceId
    void loadMessages()
  }
}

async function handleSendMessage(input: { content: string }) {
  const binding = getRemoteAgentBinding(taskId.value)
  if (!binding) return
  isSendingMessage.value = true
  try {
    const response = await remoteAgentApi.sendMessage(binding.jobId, { intent: 'auto', content: input.content }, `web-message-${crypto.randomUUID()}`)
    const merged = new Map(messages.value.map((item) => [item.message_id, item]))
    response.messages.forEach((item) => merged.set(item.message_id, item))
    messages.value = [...merged.values()].sort((left, right) => left.created_at.localeCompare(right.created_at))
    awaitingAgentReply.value = response.pending
    messagePollAttempts = 0
    if (response.pending) scheduleMessagePoll()
    if (response.workflow_patch) {
      toast.success('Agent 已在当前流程中追加专家步骤')
      await remoteAgentProvider.refresh(taskId.value).then((next) => { if (next) handleSnapshot(next) })
    } else toast.success('消息已发送，Agent 正在分析当前任务')
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '任务消息发送失败')
  } finally { isSendingMessage.value = false }
}

async function handleReplan(content: string) {
  const binding = getRemoteAgentBinding(taskId.value)
  if (!binding) return
  isSendingMessage.value = true
  try {
    const response = await remoteAgentApi.interveneJob(binding.jobId, { action: 'replan', content, confirmed: true }, `web-replan-${crypto.randomUUID()}`)
    remoteAgentProvider.close(taskId.value)
    if (response.task) restoreRemoteTaskBinding(response.task)
    else saveRemoteAgentBinding({ ...binding, jobId: response.job.job_id, requestId: response.job.request_id, createdAt: response.job.created_at })
    messages.value = []
    awaitingAgentReply.value = false
    stopMessagePoll()
    messageApiAvailable.value = true
    lastConversationEventId = ''
    toast.success('当前执行已停止，正在加载新的任务规划')
    await initializeTask()
  } catch (error) {
    toast.error(error instanceof Error ? error.message : '重新规划任务失败')
  } finally { isSendingMessage.value = false }
}

async function handleStop() {
  if (!task.value) return
  if (providerMode.value === 'remote') {
    try { const next = await remoteAgentProvider.cancel(task.value.id); if (next) handleSnapshot(next); toast.success('已提交停止请求') } catch (error) { toast.error(error instanceof Error ? error.message : '停止任务失败') }
    return
  }
  localAgentRuntime.pause(task.value.id)
  toast.success('分析已暂停')
}

async function handleRetry() {
  if (!task.value || !snapshot.value) return
  if (providerMode.value === 'remote') {
    try {
      const next = await remoteAgentProvider.retry(task.value.id)
      if (next) handleSnapshot(next)
      unsubscribe.value?.()
      unsubscribe.value = remoteAgentProvider.subscribe(task.value.id, handleSnapshot, (state) => { streamState.value = state })
      toast.success('任务已重新加入执行队列')
    } catch (error) { toast.error(error instanceof Error ? error.message : '重试任务失败') }
    return
  }
  localAgentRuntime.start(task.value.id)
  toast.success('Agent 已重新开始分析')
}

function handleModifyParams() { window.location.href = `./task-studio.html?taskId=${taskId.value}` }
function handleViewResults() {
  const params = new URLSearchParams({ taskId: taskId.value })
  if (taskId.value === competitionDemo.taskId) params.set('caseId', competitionDemo.caseId)
  window.location.href = `./risk-workspace.html?${params.toString()}`
}
function handleViewSystemHealth() { window.location.href = './system-health.html' }
function handleExportReport() {
  const binding = getRemoteAgentBinding(taskId.value)
  if (binding) window.location.href = `./audit-report.html?jobId=${encodeURIComponent(binding.jobId)}`
}
function handleLocalPause() { if (task.value) localAgentRuntime.pause(task.value.id) }
function handleLocalResume() { if (task.value) localAgentRuntime.resume(task.value.id) }
function handleLocalAdvance() { if (task.value) localAgentRuntime.advance(task.value.id) }
function handleLocalComplete() { if (task.value) localAgentRuntime.complete(task.value.id) }
async function handleArtifactDownload(artifactId: string) {
  try { window.open(await remoteAgentApi.getDownloadUrl(artifactId), '_blank', 'noopener,noreferrer') } catch (error) { toast.error(error instanceof Error ? error.message : '产物下载失败') }
}

onMounted(() => {
  void initializeTask().catch((error) => {
    loadError.value = error instanceof Error ? error.message : '任务结果初始化失败'
    toast.error(loadError.value)
  })
  isClient.value = true
})
onUnmounted(() => { unsubscribe.value?.(); stopMessagePoll(); if (providerMode.value === 'remote') remoteAgentProvider.close(taskId.value) })
</script>

<template>
  <div v-if="isClient && task && snapshot" class="page-body mx-auto max-w-[1500px] space-y-5 pb-12">
    <div class="flex items-center justify-between gap-4">
      <div><p class="text-[10px] tracking-[0.18em] text-primary">智能巡查任务</p><h1 class="mt-1 text-page-title">智能执行</h1></div>
      <a href="./task-studio.html" class="flex items-center gap-2 rounded-lg bg-muted/30 px-4 py-2 text-sm text-muted-foreground hover:bg-muted/50 hover:text-foreground"><SafeIcon name="ArrowLeft" :size="16" />返回发起巡查</a>
    </div>

    <ExecutionStatusHero :snapshot="snapshot" :task-name="task.name" :provider-mode="providerMode" />

    <AgentResultVisualization v-if="isSuccess && hasVisualResult" :snapshot="snapshot" />

    <div class="grid items-start gap-5 xl:grid-cols-2">
      <RealtimeExecutionFeed :snapshot="snapshot" :provider-mode="providerMode" :stream-state="streamState" :messages="messages" :sending="isSendingMessage" :awaiting-agent-reply="awaitingAgentReply" :interactive="messageApiAvailable" @send="handleSendMessage" @replan="handleReplan" />
      <DynamicWorkflowGraph :workflow="snapshot.workflow" />
    </div>

    <AgentPlaybackControls v-if="providerMode === 'local'" :is-running="isRunning" :is-paused="isPaused" :is-terminal="isTerminal" :progress="progress" @pause="handleLocalPause" @resume="handleLocalResume" @advance="handleLocalAdvance" @complete="handleLocalComplete" />

    <section v-if="snapshot.response && ['clarification_required', 'abstained', 'blocked'].includes(pageStatus)" class="rounded-2xl border border-amber-400/20 bg-amber-400/[0.06] p-5">
      <div class="flex items-start gap-3"><SafeIcon :name="pageStatus === 'blocked' ? 'ServerOff' : 'ShieldCheck'" :size="20" class="mt-0.5 text-amber-200" /><div><h2 class="text-sm font-semibold">{{ snapshot.response.title }}</h2><p class="mt-1 text-xs leading-5 text-muted-foreground">{{ snapshot.response.content }}</p><div class="mt-3 flex flex-wrap gap-2"><span v-for="action in snapshot.response.suggestedActions" :key="action" class="rounded-lg border border-amber-300/15 bg-amber-300/10 px-2.5 py-1.5 text-[10px] text-amber-100">{{ action }}</span></div></div></div>
    </section>

    <section v-if="snapshot.errors.length && pageStatus === 'failed'" class="rounded-2xl border border-rose-400/20 bg-rose-400/[0.06] p-5">
      <div class="flex items-start gap-3"><SafeIcon name="TriangleAlert" :size="20" class="mt-0.5 text-rose-300" /><div><h2 class="text-sm font-semibold text-rose-100">执行异常</h2><p class="mt-1 text-xs leading-5 text-rose-100/70">{{ snapshot.errors.map((error) => error.message).join('；') }}</p></div></div>
    </section>

    <section v-if="hasResultContent" class="overflow-hidden rounded-3xl border border-white/[0.08] bg-card/35 p-4 sm:p-5">
      <div class="mb-4"><h2 class="text-base font-semibold text-foreground">结果明细与证据链</h2><p class="mt-1 text-xs text-muted-foreground">查看专家解释、空间定位、质量结论与可追溯产物</p></div>
      <Tabs :default-value="defaultResultTab">
        <TabsList class="grid h-auto w-full grid-cols-3 bg-black/15 p-1">
          <TabsTrigger value="analysis" :disabled="!hasAnalysisResults" class="gap-2 py-2.5 text-xs"><SafeIcon name="ScanSearch" :size="14" />分析结果</TabsTrigger>
          <TabsTrigger value="spatial" :disabled="!hasSpatialResults" class="gap-2 py-2.5 text-xs"><SafeIcon name="MapPinned" :size="14" />空间证据</TabsTrigger>
          <TabsTrigger value="evidence" :disabled="!hasEvidenceResults" class="gap-2 py-2.5 text-xs"><SafeIcon name="PackageCheck" :size="14" />产物与质量</TabsTrigger>
        </TabsList>
        <TabsContent value="analysis" class="mt-4 space-y-4"><LanguageExpertResultCard :snapshot="snapshot" /><SemanticSceneResultCard :snapshot="snapshot" /><GeometryRelationResultCard :snapshot="snapshot" /></TabsContent>
        <TabsContent value="spatial" class="mt-4"><SpatialPositionCard :spatial="snapshot.spatial" :regions="snapshot.evidence.regions" :risks="snapshot.business.risks" /></TabsContent>
        <TabsContent value="evidence" class="mt-4 space-y-4"><QualityVerificationResultCard :snapshot="snapshot" /><AgentArtifactFeed :snapshot="snapshot" :downloadable="providerMode === 'remote'" @download="handleArtifactDownload" /></TabsContent>
      </Tabs>
    </section>

    <section v-if="isSuccess" class="relative overflow-hidden rounded-3xl border border-emerald-400/20 bg-gradient-to-r from-emerald-400/[0.08] to-cyan-400/[0.05] p-5">
      <div class="pointer-events-none absolute right-0 top-0 h-40 w-40 rounded-full bg-emerald-300/5 blur-3xl" />
      <div class="relative flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between"><div><p class="flex items-center gap-2 text-sm font-semibold text-emerald-100"><SafeIcon name="BadgeCheck" :size="18" class="text-emerald-300" />本次巡查成果已归档</p><p class="mt-1 text-xs text-muted-foreground">结果已形成可追溯证据链，可继续进入风险研判或生成审计报告。</p></div><div class="grid grid-cols-3 gap-2 text-center"><div class="rounded-xl border border-white/[0.07] bg-black/10 px-4 py-2"><strong class="block text-base text-white">{{ snapshot.business.risks.length }}</strong><span class="text-[9px] text-muted-foreground">风险候选</span></div><div class="rounded-xl border border-white/[0.07] bg-black/10 px-4 py-2"><strong class="block text-base text-white">{{ snapshot.evidence.artifacts.length }}</strong><span class="text-[9px] text-muted-foreground">证据产物</span></div><div class="rounded-xl border border-white/[0.07] bg-black/10 px-4 py-2"><strong class="block text-xs text-emerald-200">{{ qualityLabel }}</strong><span class="text-[9px] text-muted-foreground">质量结论</span></div></div></div>
    </section>

    <ActionButtons :status="pageStatus" :is-running="isRunning" :is-success="isSuccess" :is-failed="isFailed" :is-queued="isQueued" :can-view-results="canViewResults" :can-export-report="providerMode === 'remote'" @stop="handleStop" @retry="handleRetry" @modify-params="handleModifyParams" @view-results="handleViewResults" @view-system-health="handleViewSystemHealth" @export-report="handleExportReport" />

    <section class="overflow-hidden rounded-2xl border border-white/[0.07] bg-card/35">
      <button class="flex w-full items-center justify-between gap-3 p-4 text-left" @click="showTechnicalDetails = !showTechnicalDetails"><div class="flex items-center gap-2 text-sm font-medium"><SafeIcon name="FileSearch" :size="16" class="text-muted-foreground" />任务详情与完整执行记录</div><SafeIcon name="ChevronDown" :size="16" class="text-muted-foreground transition" :class="showTechnicalDetails && 'rotate-180'" /></button>
      <div v-if="showTechnicalDetails" class="space-y-4 border-t border-white/[0.07] p-4"><TaskInfoCard :task="task" /><div class="space-y-2"><div v-for="item in snapshot.trace" :key="item.traceId" class="rounded-lg bg-black/10 p-3 text-xs"><span class="text-muted-foreground">{{ item.timestamp }}</span><span class="mx-2 text-primary">{{ item.stage }}</span>{{ item.message }}</div><p v-if="!snapshot.trace.length" class="py-4 text-center text-xs text-muted-foreground">暂无执行记录</p></div></div>
    </section>
  </div>
  <div v-else-if="isClient && task && !snapshot && loadError" class="page-body flex min-h-screen items-center justify-center"><div class="surface-base card-padding max-w-md space-y-4 text-center"><SafeIcon name="CloudOff" :size="36" class="mx-auto text-amber-300" /><h1 class="text-item-title">暂时无法同步任务状态</h1><p class="text-sm leading-6 text-muted-foreground">{{ loadError }}</p><button type="button" class="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary-hover disabled:opacity-50" :disabled="isReloading" @click="handleReload"><SafeIcon name="RefreshCw" :size="15" :class="isReloading && 'animate-spin'" />{{ isReloading ? '正在重新连接' : '重新连接' }}</button></div></div>
  <div v-else-if="isClient && task && !snapshot" class="page-body flex min-h-screen items-center justify-center"><div class="surface-base card-padding max-w-md space-y-3 text-center"><SafeIcon name="Workflow" :size="36" class="mx-auto text-muted-foreground" /><h1 class="text-item-title">正在同步任务</h1><p class="text-sm text-muted-foreground">正在从智能分析服务读取规划与执行状态，请稍候。</p></div></div>
  <div v-else-if="isClient && notFound" class="page-body flex min-h-screen items-center justify-center"><div class="surface-base card-padding max-w-md text-center space-y-3"><SafeIcon name="SearchX" :size="36" class="mx-auto text-muted-foreground" /><h1 class="text-item-title">未找到任务</h1><p class="text-sm text-muted-foreground">当前任务不存在，请返回任务工作坊重新创建任务。</p><a href="./task-studio.html" class="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary-hover">返回任务工作坊</a></div></div>
  <div v-else class="flex h-screen items-center justify-center"><div class="h-12 w-12 animate-spin rounded-full border-4 border-primary/20 border-t-primary" /></div>
</template>
