<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import type { AgentPresentationSnapshot, AgentTraceView } from '@/lib/agent-presentation-types'
import type { RemoteAgentMessage } from '@/lib/remote-agent-types'
import type { RemoteStreamState } from '@/lib/remote-agent-provider'

const props = defineProps<{ snapshot: AgentPresentationSnapshot; providerMode: 'local' | 'remote'; streamState?: RemoteStreamState; messages?: RemoteAgentMessage[]; sending?: boolean; awaitingAgentReply?: boolean; interactive?: boolean }>()
const emit = defineEmits<{ send: [input: { content: string }]; replan: [content: string] }>()
const activeView = ref<'conversation' | 'activity'>('conversation')
const selectedFilter = ref<'all' | 'planning' | 'expert' | 'artifact' | 'error'>('all')
const inputText = ref('')
const pendingReplan = ref('')
const showReplanConfirm = ref(false)
const feedElement = ref<HTMLElement | null>(null)
const autoFollow = ref(true)
const activeStep = computed(() => props.snapshot.workflow?.steps.find((step) => step.status === 'running'))
const orderedEvents = computed(() => props.snapshot.trace.filter((event) => event.stage !== 'conversation_message').sort((left, right) => Number(left.traceId) - Number(right.traceId)))
const timeline = computed(() => [
  ...orderedEvents.value.map((event) => ({ id: `event-${event.traceId}`, at: event.timestamp, type: 'event' as const, event })),
  ...(props.messages || []).map((message) => ({ id: `message-${message.message_id}`, at: message.created_at, type: 'message' as const, message })),
].sort((left, right) => new Date(left.at).getTime() - new Date(right.at).getTime()))
const filteredTimeline = computed(() => timeline.value.filter((item) => {
  if (activeView.value === 'conversation') return item.type === 'message'
  if (item.type !== 'event') return false
  if (selectedFilter.value === 'all') return true
  if (selectedFilter.value === 'error') return item.event.level !== 'info'
  if (selectedFilter.value === 'expert') return item.event.category === 'expert' || item.event.category === 'quality'
  return item.event.category === selectedFilter.value
}))
const latestTime = computed(() => timeline.value.at(-1)?.at)
const conversationCount = computed(() => (props.messages?.length || 0) + 2)
const understandingItems = computed(() => {
  const task = props.snapshot.task
  const workflow = props.snapshot.workflow
  const selectedTools = props.snapshot.decision.selectedTools
  return [
    { icon: 'ScanText', label: '目标识别', content: task.objective || task.normalizedTarget || task.taskText },
    {
      icon: 'DatabaseZap',
      label: '数据核对',
      content: task.missingAssets.length
        ? `已识别 ${task.availableAssets.length} 类可用数据，仍缺少 ${task.missingAssets.join('、')}`
        : `已核对 ${task.availableAssets.length} 类任务数据，满足当前规划输入要求`,
    },
    {
      icon: 'BrainCircuit',
      label: '能力选择',
      content: selectedTools.length ? `选择 ${selectedTools.length} 项专家能力参与协作` : '正在分析任务意图并匹配专家能力',
    },
    {
      icon: 'Route',
      label: '路径生成',
      content: workflow ? `已形成 ${workflow.steps.length} 个可追踪步骤，按依赖关系执行并保留证据` : '正在生成动态执行路径',
    },
  ]
})
const filters = computed(() => [
  { id: 'all' as const, label: '全部', count: orderedEvents.value.length },
  { id: 'planning' as const, label: '规划', count: orderedEvents.value.filter((event) => event.category === 'planning').length },
  { id: 'expert' as const, label: '专家', count: orderedEvents.value.filter((event) => event.category === 'expert' || event.category === 'quality').length },
  { id: 'artifact' as const, label: '产物', count: orderedEvents.value.filter((event) => event.category === 'artifact').length },
  { id: 'error' as const, label: '异常', count: orderedEvents.value.filter((event) => event.level !== 'info').length },
])
const connection = computed(() => {
  if (props.providerMode === 'local') return { label: '预置任务记录', tone: 'text-slate-300', dot: 'bg-slate-400', pulse: false }
  if (props.streamState === 'connected') return { label: 'Agent 在线', tone: 'text-emerald-300', dot: 'bg-emerald-300', pulse: true }
  if (props.streamState === 'reconnecting') return { label: '正在重连', tone: 'text-amber-300', dot: 'bg-amber-300', pulse: true }
  if (props.streamState === 'closed') return { label: '记录已归档', tone: 'text-slate-400', dot: 'bg-slate-500', pulse: false }
  return { label: '正在连接', tone: 'text-cyan-300', dot: 'bg-cyan-300', pulse: true }
})

function formatTime(value?: string) { if (!value) return '--:--:--'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
function eventLabel(event: AgentTraceView) { if (event.category === 'planning') return '任务规划'; if (event.category === 'quality') return '质量验证'; if (event.category === 'artifact') return '产物归档'; if (event.category === 'expert') return event.toolLabel || '专家执行'; if (event.level === 'error') return '执行异常'; return '任务调度' }
function eventIcon(event: AgentTraceView) { if (event.level === 'error') return 'TriangleAlert'; if (event.level === 'warning') return 'RefreshCw'; if (event.category === 'planning') return 'BrainCircuit'; if (event.category === 'quality') return 'ShieldCheck'; if (event.category === 'artifact') return 'PackageCheck'; if (event.category === 'expert') return 'Cpu'; return 'Activity' }
function handleScroll() { const element = feedElement.value; if (element) autoFollow.value = element.scrollHeight - element.scrollTop - element.clientHeight < 36 }
async function scrollToLatest(force = false) { if (!force && !autoFollow.value) return; await nextTick(); feedElement.value?.scrollTo({ top: feedElement.value.scrollHeight, behavior: 'smooth' }) }
function submit() { const content = inputText.value.trim(); if (!content || props.sending || props.awaitingAgentReply || props.providerMode !== 'remote') return; emit('send', { content }); inputText.value = '' }
function requestReplan() { const content = inputText.value.trim(); if (!content || props.sending || props.awaitingAgentReply || props.providerMode !== 'remote') return; pendingReplan.value = content; showReplanConfirm.value = true }
function confirmReplan() { emit('replan', pendingReplan.value); inputText.value = ''; pendingReplan.value = ''; showReplanConfirm.value = false }
function handleKeydown(event: KeyboardEvent) { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() } }
watch(() => timeline.value.length, () => void scrollToLatest())
watch(selectedFilter, () => { autoFollow.value = true; void scrollToLatest(true) })
watch(activeView, () => { autoFollow.value = true; void scrollToLatest(true) })
onMounted(() => void scrollToLatest(true))
</script>

<template>
  <aside class="sticky top-4 overflow-hidden rounded-3xl border border-white/[0.09] bg-[#06121d]/95 shadow-[0_28px_80px_rgba(0,0,0,.3)] backdrop-blur-xl">
    <header class="border-b border-white/[0.07] px-5 py-4"><div class="flex items-start justify-between gap-3"><div><h2 class="flex items-center gap-2 text-base font-semibold text-white"><SafeIcon name="MessagesSquare" :size="18" class="text-cyan-300" />Agent 任务工作台</h2><p class="mt-1 text-xs text-slate-500">在执行过程中持续询问、补充信息并调整任务</p></div><span class="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-white/[0.07] bg-white/[0.035] px-2.5 py-1.5 text-[10px]" :class="connection.tone"><i class="h-1.5 w-1.5 rounded-full" :class="[connection.dot, connection.pulse && 'animate-pulse']" />{{ connection.label }}</span></div></header>
    <div v-if="activeStep" class="flex items-center gap-3 border-b border-cyan-300/10 bg-gradient-to-r from-cyan-400/[0.075] to-blue-400/[0.035] px-5 py-3"><span class="inline-flex shrink-0 items-center gap-1.5 text-[10px] tracking-[0.12em] text-cyan-400"><i class="h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-300" />当前节点</span><p class="min-w-0 flex-1 truncate text-xs font-medium text-cyan-50">{{ activeStep.title }}</p><span class="max-w-[42%] truncate font-mono text-[9px] text-cyan-200/70">{{ activeStep.executor || '等待专家节点' }}</span></div>
    <div class="grid grid-cols-2 gap-1 border-b border-white/[0.06] bg-black/10 p-1.5"><button type="button" class="flex items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-xs font-medium transition" :class="activeView === 'conversation' ? 'bg-cyan-300/10 text-cyan-100 shadow-sm' : 'text-slate-500 hover:bg-white/[0.04]'" @click="activeView = 'conversation'"><SafeIcon name="MessagesSquare" :size="14" />任务对话<span class="rounded-full bg-white/[0.06] px-1.5 py-0.5 font-mono text-[9px]">{{ conversationCount }}</span></button><button type="button" class="flex items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-xs font-medium transition" :class="activeView === 'activity' ? 'bg-blue-300/10 text-blue-100 shadow-sm' : 'text-slate-500 hover:bg-white/[0.04]'" @click="activeView = 'activity'"><SafeIcon name="Activity" :size="14" />执行动态<span class="rounded-full bg-white/[0.06] px-1.5 py-0.5 font-mono text-[9px]">{{ orderedEvents.length }}</span></button></div>
    <nav v-if="activeView === 'activity'" class="flex items-center gap-1 overflow-x-auto border-b border-white/[0.06] px-4 py-2"><button v-for="filter in filters" :key="filter.id" type="button" class="flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1.5 text-[10px] transition" :class="selectedFilter === filter.id ? 'bg-cyan-300/10 text-cyan-200' : 'text-slate-500 hover:bg-white/[0.04]'" @click="selectedFilter = filter.id">{{ filter.label }}<span class="font-mono opacity-60">{{ filter.count }}</span></button></nav>
    <div ref="feedElement" class="h-[clamp(500px,58vh,640px)] overflow-y-auto px-4 py-4" @scroll="handleScroll">
      <template v-if="activeView === 'conversation'">
        <div class="mb-4 flex justify-end">
          <div class="max-w-[90%] rounded-2xl rounded-br-md bg-cyan-500/18 px-4 py-3 text-cyan-50">
            <div class="mb-1.5 flex items-center gap-1.5 text-[10px] opacity-55"><SafeIcon name="UserRound" :size="12" />巡查目标 · {{ formatTime(snapshot.createdAt) }}</div>
            <p class="whitespace-pre-wrap text-[13px] leading-6">{{ snapshot.task.taskText }}</p>
            <span class="mt-2 inline-flex rounded-md bg-cyan-300/10 px-2 py-1 text-[9px] text-cyan-200">任务发起输入</span>
          </div>
        </div>
        <div class="mb-5 flex justify-start">
          <div class="w-[94%] rounded-2xl rounded-bl-md border border-violet-300/10 bg-gradient-to-br from-[#0d1d2b] to-violet-500/[0.035] px-4 py-3.5 text-slate-200 shadow-[0_10px_30px_rgba(0,0,0,.16)]">
            <div class="flex items-center justify-between gap-3"><div class="flex items-center gap-1.5 text-[10px] text-violet-200/70"><SafeIcon name="Bot" :size="12" />Agent 理解记录</div><span class="rounded-full border border-emerald-300/10 bg-emerald-300/[0.06] px-2 py-0.5 text-[8px] text-emerald-200/80">可审计摘要</span></div>
            <p class="mt-2 text-[13px] leading-6 text-slate-200">{{ snapshot.decision.summary }}</p>
            <div class="mt-3 grid gap-2 sm:grid-cols-2">
              <div v-for="item in understandingItems" :key="item.label" class="rounded-xl border border-white/[0.06] bg-black/10 p-3">
                <p class="flex items-center gap-1.5 text-[10px] font-medium text-cyan-200/80"><SafeIcon :name="item.icon" :size="12" />{{ item.label }}</p>
                <p class="mt-1.5 text-[10px] leading-[1.65] text-slate-400">{{ item.content }}</p>
              </div>
            </div>
          </div>
        </div>
      </template>
      <div v-if="activeView === 'conversation' && awaitingAgentReply" class="mb-4 flex justify-start">
        <div class="rounded-2xl rounded-bl-md border border-cyan-300/10 bg-[#0d1d2b] px-4 py-3 text-slate-300 shadow-[0_10px_30px_rgba(0,0,0,.16)]">
          <div class="flex items-center gap-2 text-[10px] text-cyan-200/70"><SafeIcon name="Bot" :size="12" />Agent 正在思考</div>
          <div class="mt-2 flex items-center gap-2 text-[12px] text-slate-400"><span class="flex gap-1"><i class="h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-300" /><i class="h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-300 [animation-delay:150ms]" /><i class="h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-300 [animation-delay:300ms]" /></span>正在结合任务状态、专家路径与执行证据生成回复…</div>
        </div>
      </div>
      <template v-for="item in filteredTimeline" :key="item.id">
        <div v-if="item.type === 'message'" class="mb-4 flex" :class="item.message.role === 'user' ? 'justify-end' : 'justify-start'">
          <div class="max-w-[90%] rounded-2xl px-4 py-3" :class="item.message.role === 'user' ? 'rounded-br-md bg-cyan-500/18 text-cyan-50' : item.message.role === 'system' ? 'border border-white/[0.07] bg-white/[0.035] text-slate-300' : 'rounded-bl-md border border-white/[0.08] bg-[#0d1d2b] text-slate-200 shadow-[0_10px_30px_rgba(0,0,0,.16)]'"><div class="mb-1.5 flex items-center gap-1.5 text-[10px] opacity-55"><SafeIcon :name="item.message.role === 'user' ? 'UserRound' : item.message.role === 'system' ? 'Workflow' : 'Bot'" :size="12" />{{ item.message.role === 'user' ? '人工指令' : item.message.role === 'system' ? '系统' : 'Agent' }} · {{ formatTime(item.at) }}</div><p class="whitespace-pre-wrap text-[13px] leading-6">{{ item.message.content }}</p><span v-if="item.message.intent === 'workflow_patch'" class="mt-2 inline-flex rounded-md bg-violet-300/10 px-2 py-1 text-[9px] text-violet-200">已执行：追加专家步骤</span><span v-else-if="item.message.role === 'user' && item.message.intent === 'ask'" class="mt-2 inline-flex rounded-md bg-cyan-300/10 px-2 py-1 text-[9px] text-cyan-200">已识别：状态询问</span><span v-else-if="item.message.intent === 'append_context'" class="mt-2 inline-flex rounded-md bg-amber-300/10 px-2 py-1 text-[9px] text-amber-200">已识别：补充信息</span><span v-else-if="item.message.intent === 'replan'" class="mt-2 inline-flex rounded-md bg-rose-300/10 px-2 py-1 text-[9px] text-rose-200">调整规划</span></div>
        </div>
        <div v-else class="mb-1 flex gap-3 border-b border-white/[0.04] px-1 py-2.5"><div class="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg border" :class="item.event.level === 'error' ? 'border-rose-300/20 bg-rose-300/10 text-rose-300' : item.event.level === 'warning' ? 'border-amber-300/20 bg-amber-300/10 text-amber-300' : 'border-cyan-300/15 bg-cyan-300/[0.07] text-cyan-300'"><SafeIcon :name="eventIcon(item.event)" :size="13" /></div><div class="min-w-0 flex-1"><div class="flex justify-between gap-2"><p class="truncate text-[10px] font-medium text-slate-200">{{ eventLabel(item.event) }}</p><time class="font-mono text-[9px] text-slate-600">{{ formatTime(item.at) }}</time></div><p v-if="item.event.workerId" class="mt-0.5 truncate font-mono text-[8px] text-slate-600">{{ item.event.workerId }}</p><p class="mt-1.5 text-[10px] leading-[1.55] text-slate-400">{{ item.event.message }}</p><div v-if="item.event.progress !== undefined" class="mt-2 flex items-center gap-2"><div class="h-1 flex-1 overflow-hidden rounded-full bg-white/[0.06]"><div class="h-full rounded-full bg-cyan-400/70" :style="{ width: `${item.event.progress}%` }" /></div><span class="font-mono text-[8px] text-cyan-300/70">{{ item.event.progress }}%</span></div></div></div>
      </template>
      <div v-if="!filteredTimeline.length && activeView === 'activity'" class="grid h-full place-items-center text-center"><div><SafeIcon name="Activity" :size="28" class="mx-auto text-slate-700" /><p class="mt-3 text-xs text-slate-500">等待新的任务执行动态</p></div></div>
    </div>
    <div v-if="providerMode === 'remote' && interactive" class="border-t border-white/[0.07] bg-[#071620] p-4"><div class="mb-3 flex items-center justify-between gap-3"><p class="flex items-center gap-1.5 text-[10px] text-cyan-200/70"><SafeIcon name="Sparkles" :size="12" />{{ awaitingAgentReply ? 'Agent 正在处理上一条消息' : 'Agent 将结合真实任务上下文生成回复' }}</p><span class="text-[9px] text-slate-600">Enter 发送 · Shift + Enter 换行</span></div><Textarea v-model="inputText" :disabled="sending || awaitingAgentReply" placeholder="直接输入：询问进度、补充巡查范围、排除条件或关注重点…" class="min-h-[96px] resize-none rounded-xl border-white/[0.09] bg-[#081723] px-3 py-3 text-[13px] leading-5" @focus="activeView = 'conversation'" @keydown="handleKeydown" /><div class="mt-3 flex items-center justify-between gap-2"><button type="button" class="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] text-rose-300/70 hover:bg-rose-300/[0.06] hover:text-rose-200 disabled:opacity-40" :disabled="!inputText.trim() || sending || awaitingAgentReply" @click="requestReplan"><SafeIcon name="RefreshCw" :size="12" />调整规划</button><Button size="sm" class="h-9 gap-2 px-4 text-xs" :disabled="!inputText.trim() || sending || awaitingAgentReply" @click="submit"><SafeIcon :name="sending || awaitingAgentReply ? 'LoaderCircle' : 'Send'" :size="13" :class="(sending || awaitingAgentReply) && 'animate-spin'" />{{ sending ? '发送中' : awaitingAgentReply ? 'Agent 分析中' : '发送给 Agent' }}</Button></div></div>
    <footer class="flex items-center justify-between border-t border-white/[0.06] px-4 py-2"><span class="text-[9px] text-slate-600">最后更新 {{ formatTime(latestTime) }}</span><button v-if="!autoFollow" type="button" class="text-[9px] text-cyan-300" @click="autoFollow = true; scrollToLatest(true)">回到最新</button><span v-else class="text-[9px] text-slate-600">自动跟随</span></footer>
    <AlertDialog :open="showReplanConfirm" @update:open="showReplanConfirm = $event"><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>停止当前执行并重新规划？</AlertDialogTitle><AlertDialogDescription>当前未完成的专家步骤会被安全停止，已有执行记录和产物继续保留。系统将结合原始任务、已补充上下文和本次调整创建新的规划任务。</AlertDialogDescription></AlertDialogHeader><div class="rounded-lg bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">{{ pendingReplan }}</div><AlertDialogFooter><AlertDialogCancel>继续当前任务</AlertDialogCancel><AlertDialogAction class="bg-destructive hover:bg-destructive/90" @click="confirmReplan">确认并重新规划</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </aside>
</template>
